# Conversion record: m_LOAD_DIM_EMPLOYEE → dbt

One PowerCenter mapping moved to dbt, with every rule accounted for and the result compared with the
old load row by row. All data is synthetic.

| | |
| --- | --- |
| Legacy | Repository REP_HR_DEMO, folder HR_DW, mapping `m_LOAD_DIM_EMPLOYEE`, session `s_m_LOAD_DIM_EMPLOYEE`, workflow `wf_HR_DAILY` (nightly), parameter `$$AS_OF_DATE` |
| Export | [`samples/powercenter/HR_DEMO_export.xml`](../samples/powercenter/HR_DEMO_export.xml) |
| Reads | HRIS.HR_EMPLOYEE (source), HRIS.HR_DEPARTMENT (lookup), DIM_EMPLOYEE (lookup on its own target) |
| Writes | DIM_EMPLOYEE, current state, insert or update by EMP_ID |
| dbt | `stg_hr_employees`, `stg_hr_departments` → `int_hr_departments_current` → `dim_employee` |
| Parallel run | `dbt/tests/assert_dim_employee_matches_legacy.sql`: 138 rows on both sides, 0 differences |

## How the work was split

| Step | Done by |
| --- | --- |
| Read the export: tables, the 14 rules, the workflow and the parameter | Machine (`powercenter/parser.py`, `Mapping.rules`) |
| Draft the dbt models and this rule table | Machine, with AI assistance |
| Run the tests and the parallel-run comparison, list the differences | Machine (dbt, in CI) |
| Check each rule against the export and the comparison | Person |
| Decide what to do with each data problem and each thing that does not carry over (D1–D6) | Person, by role |
| Approve the merge and the cutover | Person |

A test (`tests/test_migration.py`) fails if a rule in the export is missing from the table below, or if a
decision is not referenced in the dbt project.

## Rule by rule

| Rule in the export | Logic | In dbt | Result |
| --- | --- | --- | --- |
| `FIL_EMPLOYEES.Filter Condition` | `EMPLOYMENT_TYPE <> 'X'` | `dim_employee`: `where employment_type <> 'X'` | Same, including rows with no type (D1) |
| `EXP_DERIVE.DEPT_CODE` | `UPPER(LTRIM(RTRIM(IN_DEPT_CODE)))` | `stg_hr_employees`: `upper(trim(dept_code))` | Same |
| `EXP_DERIVE.FULL_NAME` | `LTRIM(RTRIM(LAST_NAME)) \|\| ', ' \|\| LTRIM(RTRIM(FIRST_NAME))` | trim in `stg_hr_employees`, concatenation in `dim_employee` | Same |
| `EXP_DERIVE.IS_ACTIVE` | `IIF(ISNULL(TERM_DATE) OR TERM_DATE > TO_DATE($$AS_OF_DATE, 'YYYY-MM-DD'), 'Y', 'N')` | `dim_employee`: `case` with `var('as_of_date')` | Same (D5) |
| `EXP_DERIVE.FTE_BAND` | `DECODE(TRUE, FTE >= 1, 'FULL', FTE >= 0.5, 'PART', 'SMALL')` | `dim_employee`: `case` | Same, including a missing FTE (D4) |
| `LKP_DEPARTMENT.Lookup Source Filter` | `ACTIVE_FLAG = 'Y'` | `int_hr_departments_current`: `where active_flag = 'Y'` | Same |
| `LKP_DEPARTMENT.Lookup condition` | `DEPT_CODE = IN_DEPT_CODE` | `dim_employee`: `left join` on `dept_code` | Same |
| `LKP_DEPARTMENT.Lookup policy on multiple match` | `Use Last Value` | `int_hr_departments_current`: latest `valid_from` per code | Same, confirmed from the legacy table (D3) |
| `EXP_DEFAULTS.DEPT_NAME` | `IIF(ISNULL(LKP_DEPT_NAME), 'UNKNOWN', LKP_DEPT_NAME)` | `coalesce(d.dept_name, 'UNKNOWN')` | Same (D2) |
| `EXP_DEFAULTS.COST_CENTER` | `IIF(ISNULL(LKP_COST_CENTER), '9999', LKP_COST_CENTER)` | `coalesce(d.cost_center, '9999')` | Same (D2) |
| `EXP_DEFAULTS.EMP_KEY` | `IIF(ISNULL(LKP_EMP_KEY), NEXTVAL, LKP_EMP_KEY)` | not carried over; `emp_id` is the key | Replaced (D6) |
| `EXP_DEFAULTS.LOAD_TS` | `SESSSTARTTIME` | not carried over; dbt keeps run times in its own artifacts | Replaced (D6) |
| `LKP_DIM_EMPLOYEE.Lookup condition` | `EMP_ID = IN_EMP_ID` | not needed: the model is rebuilt from the source | Replaced (D6) |
| `UPD_UPSERT.Update Strategy Expression` | `IIF(ISNULL(LKP_EMP_KEY), DD_INSERT, DD_UPDATE)` | `table` materialisation | Replaced (D6) |

Not migrated: `m_LOAD_DIM_EMPLOYEE_V1`. No workflow runs it; it is an older copy without the FTE band.
It is retired once its owner confirms.

## Decisions

The rule for every decision was **same result first, improvements after the cutover**. A migration that
also changes numbers cannot be checked against the old system.

| | Finding | Decision | Decided by | Follow-up |
| --- | --- | --- | --- | --- |
| D1 | 2 employees have no employment type. `<> 'X'` is unknown for them in both PowerCenter and SQL, so the filter drops them. | Keep: the same rows are dropped. The `not_null` test warns about them. | HR data owner | HR system owner fixes the two records. |
| D2 | 3 employees are in department QAX, which has no department row. | Keep UNKNOWN and cost centre 9999. The `relationships` test warns about them. | HR data owner, finance for the cost centre | Add QAX or move the employees. |
| D3 | OPS has two active rows after the 2026 reorganisation; the old row was never closed. Which row PowerCenter calls "last" depends on the lookup cache order, so the rule was read from the legacy table: the latest `valid_from` wins. | Write the rule down once, in `int_hr_departments_current`. The `unique` test on active rows warns. | Data modeller, confirmed by the HR data owner | HR closes the old OPS row. |
| D4 | 3 employees have no FTE; the legacy load puts them in SMALL, which understates part-time and full-time counts. | Keep SMALL for the parallel run. The `not_null` test warns. | Owner of the headcount reports | Change request after the cutover: a separate UNKNOWN band. |
| D5 | The reporting date comes from the parameter file (`$$AS_OF_DATE`). | dbt variable `as_of_date` in `dbt_project.yml`, overridden per run with `--vars`. | Data modeller | The scheduler passes the date, as the parameter file did. |
| D6 | The surrogate key EMP_KEY comes from a sequence, LOAD_TS is the session start time, and the target is maintained by insert-or-update. | Use `emp_id` as the key and rebuild the table. EMP_KEY and LOAD_TS are left out of the comparison. | Data modeller, with the consumers of DIM_EMPLOYEE | Check which reports join on EMP_KEY before cutover; keep a key map if any do. |

## Parallel run

`assert_dim_employee_matches_legacy` compares the dbt model with the legacy table on every business
column, in both directions, and returns the rows that differ. In CI it returns none: 138 rows on both
sides (150 employees less 10 external contractors and the 2 with no employment type).

Here the legacy table is simulated by `dbt/generate_hr_seeds.py`, which applies the mapping's rules as
they read in the export. In a real migration it is an unload of the old warehouse table for the same
reporting date, and then the comparison is what shows whether the rules were understood. Two things to
check with real data that this demo cannot show:

- Rows deleted from the source stay in the legacy table, because the mapping only inserts and updates.
  A rebuilt model drops them. Count them before deciding on D6.
- On large tables compare counts and per-column checksums by partition first, and rows only where those differ.
