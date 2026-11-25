"""Column-level lineage across Azure storage layers.

Builds one graph (node = stored object, edge = load) from four metadata extracts:

1. Azure Data Factory pipelines (JSON, e.g. an ARM export): Copy activity source and sink datasets.
2. Databricks Unity Catalog lineage (CSV extracts of system.access.table_lineage and column_lineage).
3. Azure SQL / SQL Server view definitions (CREATE VIEW ... SELECT ... FROM/JOIN).
4. The reporting layer mapping (report cell -> view column).

The storage type of a node is inferred from its name: abfss:// = ADLS Gen2,
catalog.schema.table = Unity Catalog, sql:<server>/... = SQL database, sftp:// = file transfer.
A *break* is a node with no known load that is not a declared source system.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

STORAGE = [
    (re.compile(r"^abfss://"), "ADLS Gen2"),
    (re.compile(r"^sftp://"), "SFTP"),
    (re.compile(r"^sql:onprem/"), "SQL Server (on-prem)"),
    (re.compile(r"^sql:azure/"), "Azure SQL Database"),
    (re.compile(r"^report:"), "Report"),
    (re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$"), "Unity Catalog (Delta)"),
]
TIER = {"SQL Server (on-prem)": 0, "SFTP": 0, "ADLS Gen2": 1, "Unity Catalog (Delta)": 2,
        "Azure SQL Database": 3, "Report": 4}


def storage_of(node: str) -> str:
    for rx, name in STORAGE:
        if rx.search(node):
            return name
    return "Unknown"


def parse_adf(path: Path) -> list[dict]:
    """ADF export: {"datasets": [{name, location}], "pipelines": [{name, properties: {activities}}]}."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ds = {d["name"]: d["location"] for d in doc.get("datasets", [])}
    edges = []
    for p in doc.get("pipelines", []):
        for a in p.get("properties", {}).get("activities", []):
            if a.get("type") != "Copy":
                continue
            for i in a.get("inputs", []):
                for o in a.get("outputs", []):
                    edges.append(dict(src=ds.get(i["referenceName"], i["referenceName"]),
                                      dst=ds.get(o["referenceName"], o["referenceName"]),
                                      via=f"ADF {p['name']}/{a['name']}", source="Azure Data Factory",
                                      when=a.get("lastRun", "")))
    return edges


def parse_uc_lineage(path: Path) -> list[dict]:
    edges = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            src = r.get("source_table_full_name") or r.get("source_path")
            dst = r.get("target_table_full_name") or r.get("target_path")
            if src and dst:
                edges.append(dict(src=src, dst=dst, via=f"{r.get('entity_type', '')} {r.get('entity_id', '')}".strip(),
                                  source="Unity Catalog", when=r.get("event_time", "")))
    return edges


def parse_uc_column_lineage(path: Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(dict(src=f"{r['source_table_full_name']}#{r['source_column_name']}",
                            dst=f"{r['target_table_full_name']}#{r['target_column_name']}"))
    return out


VIEW = re.compile(r"CREATE\s+(?:OR\s+ALTER\s+)?VIEW\s+([\w.\[\]]+)\s+AS(.*?)(?:;|\bGO\b)", re.I | re.S)
FROM_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+([\w.\[\]]+)", re.I)
SELECT = re.compile(r"SELECT(.*?)\bFROM\b(.*)", re.I | re.S)
ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+([\w.\[\]]+)\s+(?:AS\s+)?(\w+)", re.I)


def _clean(name: str) -> str:
    return name.replace("[", "").replace("]", "")


def parse_sql_views(path: Path, prefix: str) -> list[dict]:
    text = re.sub(r"--[^\n]*", "", Path(path).read_text(encoding="utf-8"))
    edges = []
    for m in VIEW.finditer(text):
        view = _clean(m.group(1))
        for s in FROM_JOIN.findall(m.group(2)):
            edges.append(dict(src=prefix + _clean(s), dst=prefix + view, via="SQL view", source="Azure SQL", when=""))
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
    """Column lineage from a view: output alias <- referenced table.column."""
    text = re.sub(r"--[^\n]*", "", Path(path).read_text(encoding="utf-8"))
    out = []
    for m in VIEW.finditer(text):
        view = _clean(m.group(1))
        sm = SELECT.search(m.group(2))
        if not sm:
            continue
        aliases = {a: _clean(t) for t, a in ALIAS.findall("FROM " + sm.group(2))}
        for expr in _split_top(sm.group(1)):
            expr = expr.strip()
            am = re.search(r"\bAS\s+(\w+)\s*$", expr, re.I)
            refs = re.findall(r"\b(\w+)\.(\w+)\b", expr)
            name = am.group(1) if am else (refs[-1][1] if refs else expr)
            for a, col in refs:
                if a in aliases:
                    out.append(dict(src=f"{prefix}{aliases[a]}#{col}", dst=f"{prefix}{view}#{name}"))
    return out


def parse_mapping(path: Path, prefix: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(dict(cell=f"report:{r['table']}/{r['row']}/{r['col']}", table=r["table"], row=r["row"],
                            col=r["col"], view=prefix + r["view"], column=r["column"]))
    return out


class Graph:
    """Table-level edges plus optional column-level edges. Tracing prefers columns when known."""

    def __init__(self, edges: list[dict], sources: set[str], col_edges: list[dict] | None = None):
        self.edges = edges
        self.sources = sources
        self.up = defaultdict(list)
        for e in edges:
            self.up[e["dst"]].append(e)
        self.col_up = defaultdict(list)
        for e in col_edges or []:
            self.col_up[e["dst"]].append(e["src"])

    def trace(self, start: str) -> tuple[list[str], list[dict], list[str]]:
        """Walk upstream from `table#column`. Returns (nodes, edges used, breaks)."""
        seen, nodes, used, breaks, stack = set(), [], [], [], [start]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            table, _, col = n.partition("#")
            if table not in nodes:
                nodes.append(table)
            if col and self.col_up.get(n):
                for src in self.col_up[n]:
                    st = src.partition("#")[0]
                    used += [e for e in self.up.get(table, []) if e["src"] == st] or [
                        dict(src=st, dst=table, via="column lineage", source="", when="")]
                    stack.append(src)
                continue
            ups = self.up.get(table, [])
            if not ups and table not in self.sources and not table.startswith("report:"):
                breaks.append(table)
            for e in ups:
                used.append(e)
                keep_col = col and storage_of(e["src"]) in ("Unity Catalog (Delta)", "Azure SQL Database")
                stack.append(f"{e['src']}#{col}" if keep_col else e["src"])
        return nodes, used, breaks
