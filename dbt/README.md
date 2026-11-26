# dbt example: from raw orders to an answer

Synthetic orders of a fictional tool wholesaler, modelled with dbt on DuckDB. The mart answers
*"List countries by sales, and where were the most drills sold, in units and euros?"*

## Run it

```
pip install "dbt-duckdb>=1.10"
cd dbt
dbt seed --profiles-dir .                                   # land the raw CSVs (stands in for ingestion)
dbt source freshness --profiles-dir .                       # are the raw orders recent enough?
dbt build --profiles-dir . --exclude "resource_type:seed"   # models, snapshot and tests
```

`python generate_seeds.py` and `python generate_hr_seeds.py` recreate the CSVs; the output is deterministic.

## Layers

| Folder | Rule | Models |
| --- | --- | --- |
| `models/staging` | One model per source table. Rename, cast, standardise; no joins, no business rules. | `stg_*` |
| `models/intermediate` | Joins and business rules several marts reuse. The currency rule lives here only. | `int_order_lines_eur` |
| `models/marts` | What consumers read: dimensions, the fact table and the answer. | `dim_*`, `fct_order_lines`, `mart_sales_by_country` |
| `snapshots` | History of changing master data (SCD type 2). | `snap_customers` |
| `tests` | Tests that span models. | `assert_mart_reconciles_to_fact`, `assert_dim_employee_matches_legacy` |
| `*/hr/` | The HR migration example: the dbt version of a PowerCenter mapping. | `stg_hr_*`, `int_hr_departments_current`, `dim_employee` |

## Decisions written down in the project

- **Sales** = delivered orders (status T), excluding VAT.
- **Currency**: euros at the rate of the order date (`int_order_lines_eur`).
- **Personal data**: the customer e-mail is tagged in `_staging.yml` and kept out of the marts.
- **Unknown products** are not dropped: the relationships test on `fct_order_lines.product_id`
  warns about them (four planted lines refer to product 999).

The `meta:` block on `mart_sales_by_country` (owner, Finnish and English synonyms, example questions)
is the metadata a natural-language query layer such as a Genie space would use.

## The HR migration example

`dim_employee` replaces the PowerCenter mapping `m_LOAD_DIM_EMPLOYEE`. The conversion record,
[`../migration/m_LOAD_DIM_EMPLOYEE.md`](../migration/m_LOAD_DIM_EMPLOYEE.md), lists every rule of the
mapping with the dbt line that replaces it and the decisions D1–D6; the code refers to them by number.

- **Reporting date**: the variable `as_of_date` in `dbt_project.yml` stands in for `$$AS_OF_DATE`;
  override it with `--vars '{as_of_date: "2026-11-30"}'`.
- **Parallel run**: `assert_dim_employee_matches_legacy` compares the model with `legacy_dim_employee`, the
  old target table, and fails on any difference.
- **Known data problems** are tests with `severity: warn`, so they stay visible without stopping the build.
- **Personal data**: birth date and e-mail are not selected in staging; the legacy target never had them.
