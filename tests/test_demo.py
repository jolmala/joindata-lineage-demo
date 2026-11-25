"""Checks on the synthetic demo. Run with:  python -m pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import demo  # noqa: E402
from lineage import graph as lg, sample  # noqa: E402
from powercenter import parser as pc  # noqa: E402


def _graph(tmp_path):
    sample.write(tmp_path)
    edges = (lg.parse_adf(tmp_path / "adf_pipelines.json") + lg.parse_uc_lineage(tmp_path / "uc_table_lineage.csv")
             + lg.parse_sql_views(tmp_path / "azure_sql_views.sql", "sql:azure/s2rpt."))
    cols = (lg.parse_uc_column_lineage(tmp_path / "uc_column_lineage.csv")
            + lg.parse_sql_view_columns(tmp_path / "azure_sql_views.sql", "sql:azure/s2rpt."))
    return lg.Graph(edges, sample.SOURCES, cols)


def test_storage_types():
    assert lg.storage_of("abfss://raw@x.dfs.core.windows.net/a/") == "ADLS Gen2"
    assert lg.storage_of("s2.gold.scr") == "Unity Catalog (Delta)"
    assert lg.storage_of("sql:azure/db.rpt.v") == "Azure SQL Database"
    assert lg.storage_of("sftp://host/file.csv") == "SFTP"


def test_view_columns_parsed(tmp_path):
    sample.write(tmp_path)
    cols = lg.parse_sql_view_columns(tmp_path / "azure_sql_views.sql", "sql:azure/s2rpt.")
    ratio = {c["src"] for c in cols if c["dst"].endswith("#solvency_ratio")}
    assert ratio == {"sql:azure/s2rpt.rpt.own_funds#total_eligible", "sql:azure/s2rpt.rpt.scr#scr"}


def test_column_level_trace_is_precise(tmp_path):
    """Share capital comes only from the capital register, not from every source of the table."""
    g = _graph(tmp_path)
    nodes, _, breaks = g.trace("sql:azure/s2rpt.rpt.v_own_funds#share_capital")
    assert {n for n in nodes if n in sample.SOURCES} == {"sql:onprem/CAPITAL.dbo.capital_instruments"}
    assert breaks == []


def test_manual_upload_is_a_break(tmp_path):
    g = _graph(tmp_path)
    _, _, breaks = g.trace("sql:azure/s2rpt.rpt.v_own_funds#subordinated_liabilities")
    assert any("/manual/subordinated_loans.xlsx" in b for b in breaks)


def test_demo_summary(tmp_path):
    s = demo.main(tmp_path)
    assert s["cells"] == 8 and s["cells_traced"] == 7
    assert s["differences"] == 2
    assert s["stale_cells"] == ["S.23.01.01 R0580", "S.23.01.01 R0620"]
    assert (tmp_path / "report.html").stat().st_size > 5000
    assert json.loads((tmp_path / "summary.json").read_text())["mappings"] == 10


def test_powercenter_export():
    maps, flows = pc.read_export(ROOT / "samples" / "powercenter" / "REP_DEMO_export.xml")
    by = {m.name: m for m in maps}
    assert sorted(by["m_FACT_TRANSACTION"].sources) == ["STG_ACCOUNT", "STG_TRANSACTION"]
    assert {w.name for w in flows} == {"wf_DWH_DAILY", "wf_REG_MONTHLY"}
    assert "m_TMP_TEST" in pc.unscheduled(maps, flows)
    up = pc.upstream(pc.lineage_edges(maps), "REG_LCR")
    assert {"TRANSACTION", "ACCOUNT", "CUSTOMER"} <= set(up)
