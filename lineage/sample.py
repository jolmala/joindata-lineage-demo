"""Synthetic metadata extracts for a fictional insurer's own-funds report.

Everything here is invented: names, timestamps and amounts. The files have the same shape as the
extracts a real Azure environment gives (ADF export, Unity Catalog system tables, view DDL, mapping).

Two problems are planted on purpose:
- a hand-uploaded spreadsheet enters the lake with no pipeline behind it (a lineage *break*);
- the SCR figure comes from an actuarial file loaded two days before the reporting date (a *stale* load).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPORT_DATE = "2026-12-31"
REPORT_TABLE = "S.23.01.01"           # own funds template, public EIOPA code
LAKE = "abfss://raw@demolake.dfs.core.windows.net"
SOURCES = {"sql:onprem/LEDGER.dbo.gl_balance", "sql:onprem/CAPITAL.dbo.capital_instruments",
           "sftp://actuarial/scr/scr_results.csv"}
ROWS = {  # report row -> view column
    "R0010": "share_capital", "R0030": "share_premium", "R0130": "reconciliation_reserve",
    "R0140": "subordinated_liabilities", "R0500": "total_available", "R0540": "total_eligible",
    "R0580": "scr", "R0620": "solvency_ratio"}
REPORTED = {"R0010": 120.0, "R0030": 35.0, "R0130": 412.6, "R0140": 80.0, "R0500": 647.6,
            "R0540": 647.6, "R0580": 301.2, "R0620": 215.0}   # EUR million, invented
WAREHOUSE = {**REPORTED, "R0580": 291.6, "R0620": 222.1}      # warehouse SCR is from the 29 Dec run


def write(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    adf = {
        "datasets": [
            {"name": "ds_gl_onprem", "location": "sql:onprem/LEDGER.dbo.gl_balance"},
            {"name": "ds_cap_onprem", "location": "sql:onprem/CAPITAL.dbo.capital_instruments"},
            {"name": "ds_scr_sftp", "location": "sftp://actuarial/scr/scr_results.csv"},
            {"name": "ds_gl_raw", "location": f"{LAKE}/gl/gl_balance/"},
            {"name": "ds_cap_raw", "location": f"{LAKE}/capital/capital_instruments/"},
            {"name": "ds_scr_raw", "location": f"{LAKE}/scr/scr_results/"},
            {"name": "ds_gold_of", "location": "s2.gold.own_funds"},
            {"name": "ds_gold_scr", "location": "s2.gold.scr"},
            {"name": "ds_sql_of", "location": "sql:azure/s2rpt.rpt.own_funds"},
            {"name": "ds_sql_scr", "location": "sql:azure/s2rpt.rpt.scr"},
        ],
        "pipelines": [
            {"name": "pl_gl_daily", "properties": {"activities": [
                {"name": "copy_gl", "type": "Copy", "inputs": [{"referenceName": "ds_gl_onprem"}],
                 "outputs": [{"referenceName": "ds_gl_raw"}], "lastRun": "2026-12-31T02:10"}]}},
            {"name": "pl_capital", "properties": {"activities": [
                {"name": "copy_cap", "type": "Copy", "inputs": [{"referenceName": "ds_cap_onprem"}],
                 "outputs": [{"referenceName": "ds_cap_raw"}], "lastRun": "2026-12-31T02:20"}]}},
            {"name": "pl_scr", "properties": {"activities": [
                {"name": "copy_scr", "type": "Copy", "inputs": [{"referenceName": "ds_scr_sftp"}],
                 "outputs": [{"referenceName": "ds_scr_raw"}], "lastRun": "2026-12-29T22:00"}]}},
            {"name": "pl_to_reporting", "properties": {"activities": [
                {"name": "copy_of", "type": "Copy", "inputs": [{"referenceName": "ds_gold_of"}],
                 "outputs": [{"referenceName": "ds_sql_of"}], "lastRun": "2026-12-31T05:00"},
                {"name": "copy_scr", "type": "Copy", "inputs": [{"referenceName": "ds_gold_scr"}],
                 "outputs": [{"referenceName": "ds_sql_scr"}], "lastRun": "2026-12-31T05:00"}]}},
        ]}
    (d / "adf_pipelines.json").write_text(json.dumps(adf, indent=1), encoding="utf-8")

    uc = [
        ("", f"{LAKE}/gl/gl_balance/", "s2.bronze.gl_balance", "JOB", "load_bronze", "2026-12-31T03:00"),
        ("", f"{LAKE}/capital/capital_instruments/", "s2.bronze.capital_instruments", "JOB", "load_bronze", "2026-12-31T03:00"),
        ("", f"{LAKE}/scr/scr_results/", "s2.bronze.scr_results", "JOB", "load_bronze", "2026-12-30T03:00"),
        ("", "abfss://landing@demolake.dfs.core.windows.net/manual/subordinated_loans.xlsx",
         "s2.bronze.subordinated_loans", "NOTEBOOK", "manual_upload", "2026-12-31T03:05"),
        ("s2.bronze.gl_balance", "", "s2.silver.own_fund_items", "JOB", "build_silver", "2026-12-31T04:00"),
        ("s2.bronze.capital_instruments", "", "s2.silver.own_fund_items", "JOB", "build_silver", "2026-12-31T04:00"),
        ("s2.bronze.subordinated_loans", "", "s2.silver.own_fund_items", "JOB", "build_silver", "2026-12-31T04:00"),
        ("s2.silver.own_fund_items", "", "s2.gold.own_funds", "JOB", "build_gold", "2026-12-31T04:30"),
        ("s2.bronze.scr_results", "", "s2.gold.scr", "JOB", "build_gold", "2026-12-30T04:30"),
    ]
    with open(d / "uc_table_lineage.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source_table_full_name", "source_path", "target_table_full_name", "entity_type", "entity_id", "event_time"])
        for s, p, t, et, eid, ts in uc:
            w.writerow([s, p if not s else "", t, et, eid, ts])

    col = [
        ("s2.bronze.gl_balance", "reserve_amount", "s2.silver.own_fund_items", "reconciliation_reserve"),
        ("s2.bronze.capital_instruments", "nominal", "s2.silver.own_fund_items", "share_capital"),
        ("s2.bronze.capital_instruments", "premium", "s2.silver.own_fund_items", "share_premium"),
        ("s2.bronze.subordinated_loans", "amount", "s2.silver.own_fund_items", "subordinated_liabilities"),
        ("s2.bronze.scr_results", "scr_amount", "s2.gold.scr", "scr"),
    ]
    items = ("share_capital", "share_premium", "reconciliation_reserve", "subordinated_liabilities")
    col += [("s2.silver.own_fund_items", c, "s2.gold.own_funds", c) for c in items]
    col += [("s2.silver.own_fund_items", c, "s2.gold.own_funds", t) for t in ("total_available", "total_eligible") for c in items]
    with open(d / "uc_column_lineage.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source_table_full_name", "source_column_name", "target_table_full_name", "target_column_name"])
        w.writerows(col)

    (d / "azure_sql_views.sql").write_text("""-- Reporting mart (Azure SQL Database s2rpt)
CREATE OR ALTER VIEW rpt.v_own_funds AS
SELECT o.share_capital, o.share_premium, o.reconciliation_reserve, o.subordinated_liabilities,
       o.total_available, o.total_eligible, s.scr, o.total_eligible / NULLIF(s.scr, 0) * 100 AS solvency_ratio
FROM rpt.own_funds o
JOIN rpt.scr s ON s.entity_id = o.entity_id;
GO
""", encoding="utf-8")

    with open(d / "report_mapping.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["table", "row", "col", "view", "column"])
        for r, c in ROWS.items():
            w.writerow([REPORT_TABLE, r, "C0010", "s2rpt.rpt.v_own_funds", c])
