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

## dbt example: from raw orders to an answer

`dbt/` is a small dbt project on DuckDB with synthetic orders of a fictional tool wholesaler. It answers the
question *"List countries by sales, and where were the most drills sold, in units and euros?"* and shows
the pieces that make such an answer trustworthy:

| Piece | Where |
| --- | --- |
| Layers: staging → intermediate → marts | `dbt/models/` |
| Tests: unique, not_null, relationships, accepted_values | `_staging.yml`, `_intermediate.yml`, `_marts.yml` |
| Reconciliation test: the mart total equals the fact table, to the cent | `dbt/tests/assert_mart_reconciles_to_fact.sql` |
| Currency rule written down once: euros at the order-date rate | `int_order_lines_eur.sql`, mart description |
| Incremental fact table (reloads the last 7 days of orders) | `fct_order_lines.sql` |
| Customer history (SCD type 2) | `dbt/snapshots/snap_customers.sql` |
| Metadata for natural-language querying: synonyms, example questions, owner, personal-data tag | `meta:` in `_marts.yml` and `_staging.yml` |
| A planted problem: four order lines refer to a product that does not exist | reported as a warning by the relationships test |

Run it (Python 3.10+):

```
pip install "dbt-duckdb>=1.10"
cd dbt
python generate_seeds.py          # optional: the CSVs are already in seeds/
dbt build --profiles-dir .        # seeds, models, snapshot and tests
```

The **dbt** job in GitHub Actions runs the same steps, prints the answer and uploads the dbt documentation
as the **dbt-docs** artifact. Expected answer, delivered orders in euros:

| Country | Drills, units | Drills, EUR | All sales, EUR |
| --- | ---: | ---: | ---: |
| Finland | 1 883 | 334 067 | 747 530 |
| Germany | 904 | 160 176 | 426 721 |
| Netherlands | 746 | 139 054 | 261 013 |
| Sweden | 467 | 82 670 | 191 520 |
| United States | 482 | 81 299 | 210 568 |
| Estonia | 176 | 29 274 | 76 804 |

## Layout

```
lineage/graph.py        parsers for ADF, Unity Catalog lineage, SQL views, report mapping; the lineage graph
lineage/sample.py       synthetic extracts for a fictional insurer's own-funds report
powercenter/parser.py   minimal PowerCenter XML export reader
samples/powercenter/    synthetic repository export
demo.py                 runs both parts and writes the HTML report
pyproject.toml          pytest and ruff settings
dbt/                    dbt project: synthetic orders, models, tests, snapshot
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
