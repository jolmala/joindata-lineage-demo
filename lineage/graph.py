"""Column-level lineage across Azure storage layers.

Builds one graph (node = stored object, edge = load) from four metadata extracts:

1. Azure Data Factory pipelines (JSON, e.g. an ARM export): Copy activity source and sink datasets.
2. Databricks Unity Catalog lineage (CSV extracts of system.access.table_lineage and column_lineage).
3. Azure SQL / SQL Server view definitions (CREATE VIEW ... SELECT ... FROM/JOIN).
4. The reporting layer mapping (report cell -> view column).

The storage type of a node is inferred from its name: abfss:// = ADLS Gen2,
catalog.schema.table = Unity Catalog, sql:<server>/... = SQL database, sftp:// = file transfer.
A *break* is a node with no known load that is not a declared source system.

Node naming: a table-level node is the object name (``s2.gold.scr``); a column-level node adds
``#column`` (``s2.gold.scr#scr``). Edges are plain dicts with the keys ``src``, ``dst``, ``via``
(what performed the load), ``source`` (which extract the edge came from) and ``when`` (last run).
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

# Storage type by node-name pattern. The first match wins, so the generic three-part
# Unity Catalog name is checked last.
STORAGE = [
    (re.compile(r"^abfss://"), "ADLS Gen2"),
    (re.compile(r"^sftp://"), "SFTP"),
    (re.compile(r"^sql:onprem/"), "SQL Server (on-prem)"),
    (re.compile(r"^sql:azure/"), "Azure SQL Database"),
    (re.compile(r"^report:"), "Report"),
    (re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$"), "Unity Catalog (Delta)"),
]

# Left-to-right order of storage types in the report (0 = source systems, 4 = report).
TIER = {
    "SQL Server (on-prem)": 0,
    "SFTP": 0,
    "ADLS Gen2": 1,
    "Unity Catalog (Delta)": 2,
    "Azure SQL Database": 3,
    "Report": 4,
}


def storage_of(node: str) -> str:
    """Return the storage type of a node name, or "Unknown" if no pattern matches."""
    for pattern, name in STORAGE:
        if pattern.search(node):
            return name
    return "Unknown"


# --------------------------------------------------------------------------- extract parsers


def parse_adf(path: Path) -> list[dict]:
    """Table-level edges from a Data Factory export.

    Expected shape: ``{"datasets": [{name, location}], "pipelines": [{name, properties: {activities}}]}``.
    Only Copy activities are read; each input dataset is linked to each output dataset. Dataset
    names are resolved to their storage location so that edges join up with the other extracts.
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    location = {d["name"]: d["location"] for d in doc.get("datasets", [])}
    edges = []
    for pipeline in doc.get("pipelines", []):
        for activity in pipeline.get("properties", {}).get("activities", []):
            if activity.get("type") != "Copy":
                continue
            for inp in activity.get("inputs", []):
                for out in activity.get("outputs", []):
                    edges.append(
                        dict(
                            src=location.get(inp["referenceName"], inp["referenceName"]),
                            dst=location.get(out["referenceName"], out["referenceName"]),
                            via=f"ADF {pipeline['name']}/{activity['name']}",
                            source="Azure Data Factory",
                            when=activity.get("lastRun", ""),
                        )
                    )
    return edges


def parse_uc_lineage(path: Path) -> list[dict]:
    """Table-level edges from a CSV extract of ``system.access.table_lineage``.

    A row's source is either a table (``source_table_full_name``) or a storage path
    (``source_path``, e.g. files read from ADLS); the same applies to the target.
    Rows without both ends are skipped.
    """
    edges = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            src = row.get("source_table_full_name") or row.get("source_path")
            dst = row.get("target_table_full_name") or row.get("target_path")
            if src and dst:
                edges.append(
                    dict(
                        src=src,
                        dst=dst,
                        via=f"{row.get('entity_type', '')} {row.get('entity_id', '')}".strip(),
                        source="Unity Catalog",
                        when=row.get("event_time", ""),
                    )
                )
    return edges


def parse_uc_column_lineage(path: Path) -> list[dict]:
    """Column-level edges (``src``/``dst`` as ``table#column``) from ``system.access.column_lineage``."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(
                dict(
                    src=f"{row['source_table_full_name']}#{row['source_column_name']}",
                    dst=f"{row['target_table_full_name']}#{row['target_column_name']}",
                )
            )
    return out


# SQL view parsing is deliberately simple (regular expressions, not a SQL parser). It handles one
# SELECT ... FROM ... JOIN per view with table aliases. Not supported: subqueries, CTEs, UNION,
# SELECT *, and column references without a table alias. Views outside that shape yield fewer or
# no column edges; table-level edges from FROM/JOIN are still found.
VIEW = re.compile(r"CREATE\s+(?:OR\s+ALTER\s+)?VIEW\s+([\w.\[\]]+)\s+AS(.*?)(?:;|\bGO\b)", re.I | re.S)
FROM_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+([\w.\[\]]+)", re.I)
SELECT = re.compile(r"SELECT(.*?)\bFROM\b(.*)", re.I | re.S)
ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+([\w.\[\]]+)\s+(?:AS\s+)?(\w+)", re.I)


def _clean(name: str) -> str:
    """Drop T-SQL square brackets: ``[rpt].[scr]`` -> ``rpt.scr``."""
    return name.replace("[", "").replace("]", "")


def _strip_comments(text: str) -> str:
    """Remove ``--`` line comments so commented-out tables are not picked up."""
    return re.sub(r"--[^\n]*", "", text)


def parse_sql_views(path: Path, prefix: str) -> list[dict]:
    """Table-level edges from view DDL: every table in FROM/JOIN feeds the view.

    ``prefix`` places the names in the graph's namespace, e.g. ``"sql:azure/s2rpt."``.
    """
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
    edges = []
    for m in VIEW.finditer(text):
        view = _clean(m.group(1))
        for table in FROM_JOIN.findall(m.group(2)):
            edges.append(
                dict(
                    src=prefix + _clean(table), dst=prefix + view, via="SQL view", source="Azure SQL", when=""
                )
            )
    return edges


def _split_top(text: str) -> list[str]:
    """Split a select list on commas that are not inside parentheses."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def parse_sql_view_columns(path: Path, prefix: str) -> list[dict]:
    """Column-level edges from view DDL: output column <- each ``alias.column`` it references.

    The output name is the ``AS`` alias if there is one, otherwise the last referenced column
    (``o.share_capital`` -> ``share_capital``). An expression such as
    ``o.total_eligible / s.scr * 100 AS solvency_ratio`` gives one edge per referenced column.
    See the note above ``VIEW`` for what is not supported.
    """
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
    out = []
    for m in VIEW.finditer(text):
        view = _clean(m.group(1))
        select = SELECT.search(m.group(2))
        if not select:
            continue
        # alias -> table, from the FROM/JOIN part of the statement
        aliases = {alias: _clean(table) for table, alias in ALIAS.findall("FROM " + select.group(2))}
        for expr in _split_top(select.group(1)):
            expr = expr.strip()
            as_name = re.search(r"\bAS\s+(\w+)\s*$", expr, re.I)
            refs = re.findall(r"\b(\w+)\.(\w+)\b", expr)  # (alias, column) pairs
            name = as_name.group(1) if as_name else (refs[-1][1] if refs else expr)
            for alias, column in refs:
                if alias in aliases:
                    out.append(dict(src=f"{prefix}{aliases[alias]}#{column}", dst=f"{prefix}{view}#{name}"))
    return out


def parse_mapping(path: Path, prefix: str) -> list[dict]:
    """Report cells and the view column each one is filled from.

    CSV columns: ``table, row, col, view, column``. The cell becomes a ``report:`` node so that
    it can be the starting point of a trace.
    """
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(
                dict(
                    cell=f"report:{row['table']}/{row['row']}/{row['col']}",
                    table=row["table"],
                    row=row["row"],
                    col=row["col"],
                    view=prefix + row["view"],
                    column=row["column"],
                )
            )
    return out


# --------------------------------------------------------------------------- graph


class Graph:
    """Table-level edges plus optional column-level edges. Tracing prefers columns when known.

    ``sources`` are the declared source systems: a trace that ends there is complete. A trace
    that ends anywhere else is reported as a break.
    """

    def __init__(self, edges: list[dict], sources: set[str], col_edges: list[dict] | None = None):
        self.edges = edges
        self.sources = sources
        # Upstream indexes: target -> incoming table edges / source columns.
        self.up: dict[str, list[dict]] = defaultdict(list)
        for edge in edges:
            self.up[edge["dst"]].append(edge)
        self.col_up: dict[str, list[str]] = defaultdict(list)
        for edge in col_edges or []:
            self.col_up[edge["dst"]].append(edge["src"])

    def trace(self, start: str) -> tuple[list[str], list[dict], list[str]]:
        """Walk upstream from ``table#column`` (or a bare table). Returns (nodes, edges used, breaks).

        ``nodes`` are table-level names in visiting order, ``edges`` are the loads the trace went
        through and ``breaks`` are tables with no known load that are not declared sources.
        """
        seen: set[str] = set()
        nodes: list[str] = []
        used: list[dict] = []
        breaks: list[str] = []
        stack = [start]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            table, _, col = current.partition("#")
            if table not in nodes:
                nodes.append(table)

            # 1) Column lineage known for this column: follow only those columns. This is what
            #    keeps the trace precise (share capital leads to the capital register only, not to
            #    every table that feeds the same silver table).
            if col and self.col_up.get(current):
                for src in self.col_up[current]:
                    src_table = src.partition("#")[0]
                    # Record the matching table-level edge so the report can show how it was
                    # loaded; if there is none, record a synthetic column-lineage edge.
                    matching = [e for e in self.up.get(table, []) if e["src"] == src_table]
                    used += matching or [
                        dict(src=src_table, dst=table, via="column lineage", source="", when="")
                    ]
                    stack.append(src)
                continue

            # 2) Otherwise fall back to table lineage. No incoming load at all means the data
            #    appears from nowhere: a break, unless the table is a declared source.
            ups = self.up.get(table, [])
            if not ups and table not in self.sources and not table.startswith("report:"):
                breaks.append(table)
            for edge in ups:
                used.append(edge)
                # Carry the column name upstream only where column lineage can exist (Unity Catalog
                # and SQL objects). Files and source systems are tracked at table level.
                keep_col = col and storage_of(edge["src"]) in ("Unity Catalog (Delta)", "Azure SQL Database")
                stack.append(f"{edge['src']}#{col}" if keep_col else edge["src"])
        return nodes, used, breaks
