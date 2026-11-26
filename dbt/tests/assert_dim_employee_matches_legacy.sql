-- Parallel run: the dbt model must return exactly the rows the legacy PowerCenter load produced.
-- Compared on every business column. EMP_KEY (sequence) and LOAD_TS (run time) are left out (D6).
-- Returns the differing rows, labelled by side, so an empty result means the test passes.
with new_rows as (
    select emp_id, full_name, dept_code, dept_name, cost_center, job_code,
           employment_type, hire_date, term_date, is_active, fte_band
    from {{ ref('dim_employee') }}
),

old_rows as (
    select emp_id, full_name, dept_code, dept_name, cast(cost_center as varchar) as cost_center,
           job_code, employment_type, cast(hire_date as date) as hire_date,
           cast(term_date as date) as term_date, is_active, fte_band
    from {{ source('legacy_dw', 'legacy_dim_employee') }}
),

only_new as (select * from new_rows except select * from old_rows),
only_old as (select * from old_rows except select * from new_rows)

select 'only in dbt' as side, * from only_new
union all
select 'only in legacy' as side, * from only_old
