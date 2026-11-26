# Regulatory lineage demo

Traces every figure of a regulatory report back to its source system, through the storage layers of an Azure data platform, and reconciles reported values against the warehouse. A second part reads an Informatica PowerCenter repository export and shows mappings, lineage and objects that no workflow runs.

All data is synthetic. Nothing here comes from a client.

![Report: lineage graph and reconciliation](docs/screenshot.png)

## What it shows

| Question | How the demo answers it |
| --- | --- |
| Where does this reported number come from? | Builds one graph from Data Factory pipelines, Unity Catalog table and column lineage, SQL view definitions and the report mapping, then walks it at column level from each report cell to the source tables. |
| Is there data in the chain that nobody loads? | Flags *breaks*: objects with no known load that are not declared sources. In the demo, a hand-uploaded spreadsheet feeds subordinated liabilities. |
| Why does the report differ from the warehouse? | Reconciles each cell and uses the load timestamps on the lineage path to explain the gap. In the demo, the SCR comes from an actuarial file loaded two days before the reporting date. |
| What does a PowerCenter estate actually contain? | Lists mappings with sources, targets and logic steps, follows table lineage across mappings and lists mappings no workflow runs. |

## Run it

Python 3.10 or later. No third-party packages are needed for the demo; the tests use pytest and
the code style is checked with ruff (settings in `pyproject.toml`).

```
python demo.py              # writes out/report.html and out/summary.json
python -m pytest -q         # 6 checks
ruff check . && ruff format --check .
```

Or without installing anything: open **Actions → tests → Run workflow** on GitHub. When the run finishes, download **demo-report** from the run page and open `report.html`.

## Layout

```
lineage/graph.py        parsers for ADF, Unity Catalog lineage, SQL views, report mapping; the lineage graph
lineage/sample.py       synthetic extracts for a fictional insurer's own-funds report
powercenter/parser.py   minimal PowerCenter XML export reader
samples/powercenter/    synthetic repository export
demo.py                 runs both parts and writes the HTML report
pyproject.toml          pytest and ruff settings
tests/                  checks on parsing, column-level tracing, breaks and reconciliation
docs/                   screenshots, AI working method, agent governance model
```

## Using it on a real platform

The inputs are metadata extracts, not data:

- Data Factory: an ARM export or `az datafactory pipeline show` output, reduced to datasets and Copy activities.
- Unity Catalog: `system.access.table_lineage` and `system.access.column_lineage` as CSV.
- SQL views: `sys.sql_modules` definitions.
- Report mapping: cell to view column, from the reporting tool.

Only object names and timestamps are read. Figures for reconciliation come from the report and the warehouse at the same reporting date.

## Scope

This is a reduced, illustrative version. The classification rules, effort estimates, SSIS and Databricks analysis, EBA and Solvency II taxonomy handling, and run-history analysis used in client work are not included.

## How it was built

Written with Claude Code as a pair programmer. Every module has a test, the expected results were defined before the code, and output was checked against the synthetic reference data. See [docs/how-ai-was-used.md](docs/how-ai-was-used.md).

## Governed AI agents

The same discipline applies to agents that run unattended. [docs/agent-governance.md](docs/agent-governance.md) describes the control model of a personal market-monitoring system: read-only access, no credentials for agents, scoped and version-checked writes, signed prompts, and a person for anything irreversible. It includes a synthetic example run. The system's code is not published.

## Author

Jani Olmala, [Joindata Oy](https://www.joindata.fi), Oulu, Finland · [LinkedIn](https://www.linkedin.com/in/jani-olmala-0a02788/)

© 2026 Joindata Oy. No open-source licence is granted; you are welcome to read and run the code to evaluate it.
