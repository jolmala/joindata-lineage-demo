"""Checks that tie the HR migration example together: export, conversion record and dbt project."""

import re
from pathlib import Path

from powercenter import parser as pc

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "samples" / "powercenter" / "HR_DEMO_export.xml"
RECORD = ROOT / "migration" / "m_LOAD_DIM_EMPLOYEE.md"


def _mapping():
    maps, flows = pc.read_export(EXPORT)
    return {m.name: m for m in maps}["m_LOAD_DIM_EMPLOYEE"], maps, flows


def test_hr_export_inventory():
    """Source, target and lookup tables are read, and the old version is found unscheduled."""
    m, maps, flows = _mapping()
    assert m.sources == ["HR_EMPLOYEE"] and m.targets == ["DIM_EMPLOYEE"]
    assert m.lookups == ["HR_DEPARTMENT", "DIM_EMPLOYEE"]
    assert pc.unscheduled(maps, flows) == ["m_LOAD_DIM_EMPLOYEE_V1"]


def test_every_rule_is_in_the_conversion_record():
    """No rule of the mapping is left out: each one appears by id in the conversion record."""
    m, _, _ = _mapping()
    record = RECORD.read_text(encoding="utf-8")
    missing = [r.id for r in m.rules if f"`{r.id}`" not in record]
    assert len(m.rules) == 14
    assert missing == []


def test_every_decision_is_referenced_in_the_dbt_project():
    """Each decision D1-D6 in the record is referenced from the dbt code or tests that implement it."""
    record = RECORD.read_text(encoding="utf-8")
    decisions = sorted(set(re.findall(r"\bD[1-9]\b", record)))
    code = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "dbt").rglob("*")
        if p.suffix in {".sql", ".yml"} and "target" not in p.parts
    )
    assert decisions == ["D1", "D2", "D3", "D4", "D5", "D6"]
    assert [d for d in decisions if not re.search(rf"\b{d}\b", code)] == []
