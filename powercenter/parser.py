"""Minimal Informatica PowerCenter XML export reader.

Reads a repository export (pmrep objectexport / Designer export) and returns, per mapping:
source and target tables, transformation counts by type, and table-level lineage edges.
It also lists workflows and the sessions they run.

This is a reduced, illustrative version. Classification rules, effort estimates and the SQL
override analysis used in client work are not included.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

PASSIVE_IO = {"Source Definition", "Target Definition", "Source Qualifier",
              "Input Transformation", "Output Transformation"}


@dataclass
class Mapping:
    folder: str
    name: str
    sources: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    transformations: Counter = field(default_factory=Counter)

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
    folder: str
    name: str
    sessions: list[tuple[str, str]] = field(default_factory=list)   # (session, mapping)


def _parse(path: Path) -> ET.Element:
    # Exports reference powrmart.dtd; ElementTree ignores the DOCTYPE and does not fetch it.
    return ET.parse(path).getroot()


def read_export(path: Path) -> tuple[list[Mapping], list[Workflow]]:
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
            mappings.append(mp)
        for wf in folder.findall("WORKFLOW"):
            w = Workflow(folder=fname, name=wf.get("NAME", ""))
            for ti in wf.findall("TASKINSTANCE"):
                if ti.get("TASKTYPE") == "Session":
                    task = ti.get("TASKNAME", "")
                    w.sessions.append((task, sessions.get(task, "")))
            workflows.append(w)
    return mappings, workflows


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
