"""Minimal Informatica PowerCenter XML export reader.

Reads a repository export (pmrep objectexport / Designer export) and returns, per mapping:
source, target and lookup tables, transformation counts by type, the logic written in the
mapping (expressions, filters, lookup conditions) and table-level lineage edges.
It also lists workflows and the sessions they run.

This is a reduced, illustrative version. Classification rules, effort estimates and the SQL
override analysis used in client work are not included.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Transformation attributes that carry logic a migration has to reproduce.
LOGIC_ATTRIBUTES = {
    "Sql Query",
    "Source Filter",
    "Filter Condition",
    "Join Condition",
    "Lookup Sql Override",
    "Lookup Source Filter",
    "Lookup condition",
    "Lookup policy on multiple match",
    "Update Strategy Expression",
}

PASSIVE_IO = {
    "Source Definition",
    "Target Definition",
    "Source Qualifier",
    "Input Transformation",
    "Output Transformation",
}


@dataclass
class Rule:
    """One piece of mapping logic: an output port's expression or a logic-bearing attribute."""

    transformation: str
    item: str  # port name, or attribute name such as "Filter Condition"
    logic: str

    @property
    def id(self) -> str:
        """Stable reference used in conversion records, e.g. EXP_DERIVE.FULL_NAME."""
        return f"{self.transformation}.{self.item}"


@dataclass
class Mapping:
    """One mapping: the tables it reads and writes, and how many of each transformation type it has."""

    folder: str
    name: str
    sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    lookups: list[str] = field(default_factory=list)
    transformations: Counter = field(default_factory=Counter)
    rules: list[Rule] = field(default_factory=list)

    @property
    def logic_steps(self) -> int:
        """Transformations that carry logic (sources, targets and qualifiers excluded)."""
        return sum(n for t, n in self.transformations.items() if t not in PASSIVE_IO)

    @property
    def size(self) -> str:
        """Rough size band by number of logic steps; a starting point for review, not an estimate."""
        n = self.logic_steps
        return "small" if n <= 5 else "medium" if n <= 15 else "large"


@dataclass
class Workflow:
    """One workflow and the sessions it runs, as (session name, mapping name) pairs."""

    folder: str
    name: str
    sessions: list[tuple[str, str]] = field(default_factory=list)  # (session, mapping)


def _parse(path: Path) -> ET.Element:
    """Parse the export file and return the root element."""
    # Exports reference powrmart.dtd; ElementTree ignores the DOCTYPE and does not fetch it.
    return ET.parse(path).getroot()


def read_export(path: Path) -> tuple[list[Mapping], list[Workflow]]:
    """Read mappings and workflows from every FOLDER in a repository export.

    Sources and targets are taken from the mapping's Source/Target Definition instances;
    lookup tables from the "Lookup table name" attribute of its Lookup transformations.
    A workflow's sessions are linked to mappings through the folder's SESSION elements,
    because TASKINSTANCE only names the session, not the mapping it runs.
    """
    root = _parse(Path(path))
    mappings, workflows = [], []
    for folder in root.iter("FOLDER"):
        fname = folder.get("NAME", "")
        sessions = {s.get("NAME"): s.get("MAPPINGNAME") for s in folder.iter("SESSION")}
        for m in folder.findall("MAPPING"):
            mp = Mapping(folder=fname, name=m.get("NAME", ""))
            for inst in m.findall("INSTANCE"):
                ttype = inst.get("TRANSFORMATION_TYPE", "")
                mp.transformations[ttype] += 1
                if ttype == "Source Definition":
                    mp.sources.append(inst.get("TRANSFORMATION_NAME", ""))
                elif ttype == "Target Definition":
                    mp.targets.append(inst.get("TRANSFORMATION_NAME", ""))
            for t in m.findall("TRANSFORMATION"):
                attrs = {a.get("NAME"): a.get("VALUE", "") for a in t.findall("TABLEATTRIBUTE")}
                if t.get("TYPE") == "Lookup Procedure" and attrs.get("Lookup table name"):
                    mp.lookups.append(attrs["Lookup table name"])
                mp.rules += _rules(t, attrs)
            mappings.append(mp)
        for wf in folder.findall("WORKFLOW"):
            w = Workflow(folder=fname, name=wf.get("NAME", ""))
            for ti in wf.findall("TASKINSTANCE"):
                if ti.get("TASKTYPE") == "Session":
                    task = ti.get("TASKNAME", "")
                    w.sessions.append((task, sessions.get(task, "")))
            workflows.append(w)
    return mappings, workflows


def _rules(t: ET.Element, attrs: dict[str, str]) -> list[Rule]:
    """Logic in one transformation: port expressions that compute something, then logic attributes."""
    name = t.get("NAME", "")
    out = [
        Rule(name, f.get("NAME", ""), f.get("EXPRESSION", ""))
        for f in t.findall("TRANSFORMFIELD")
        if f.get("EXPRESSION") and f.get("EXPRESSION") != f.get("NAME")
    ]
    out += [Rule(name, k, v) for k, v in attrs.items() if k in LOGIC_ATTRIBUTES and v]
    return out


def lineage_edges(mappings: list[Mapping]) -> list[tuple[str, str, str]]:
    """(source table, target table, mapping) for every source-target pair in a mapping."""
    return [(s, t, m.name) for m in mappings for s in sorted(set(m.sources)) for t in sorted(set(m.targets))]


def upstream(edges: list[tuple[str, str, str]], table: str) -> list[str]:
    """All tables a target depends on, through any number of mappings."""
    up: dict[str, set[str]] = {}
    for s, t, _ in edges:
        up.setdefault(t, set()).add(s)
    seen, stack = [], [table]
    while stack:
        n = stack.pop()
        for s in sorted(up.get(n, ())):
            if s not in seen:
                seen.append(s)
                stack.append(s)
    return seen


def unscheduled(mappings: list[Mapping], workflows: list[Workflow]) -> list[str]:
    """Mappings that no workflow runs: candidates to drop before a migration, after review."""
    used = {m for w in workflows for _, m in w.sessions}
    return [m.name for m in mappings if m.name not in used]
