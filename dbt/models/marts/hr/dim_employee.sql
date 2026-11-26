-- Employee dimension, current state. dbt version of the PowerCenter mapping m_LOAD_DIM_EMPLOYEE.
-- Each rule names the mapping object it replaces; migration/m_LOAD_DIM_EMPLOYEE.md has the full record.
with employees as (
    select *
    from {{ ref('stg_hr_employees') }}
    -- FIL_EMPLOYEES.Filter Condition: EMPLOYMENT_TYPE <> 'X'. A missing type also drops the row,
    -- as it did in PowerCenter (D1).
    where employment_type <> 'X'
)

select
    e.emp_id,
    e.last_name || ', ' || e.first_name as full_name,  -- EXP_DERIVE.FULL_NAME
    e.dept_code,  -- EXP_DERIVE.DEPT_CODE, trimmed in staging
    coalesce(d.dept_name, 'UNKNOWN') as dept_name,  -- EXP_DEFAULTS.DEPT_NAME (D2)
    coalesce(d.cost_center, '9999') as cost_center,  -- EXP_DEFAULTS.COST_CENTER (D2)
    e.job_code,
    e.employment_type,
    e.hire_date,
    e.term_date,
    case  -- EXP_DERIVE.IS_ACTIVE, with $$AS_OF_DATE as the dbt variable as_of_date (D5)
        when e.term_date is null or e.term_date > cast('{{ var("as_of_date") }}' as date) then 'Y'
        else 'N'
    end as is_active,
    case  -- EXP_DERIVE.FTE_BAND; a missing FTE falls to SMALL, as in PowerCenter (D4)
        when e.fte >= 1 then 'FULL'
        when e.fte >= 0.5 then 'PART'
        else 'SMALL'
    end as fte_band
from employees as e
left join {{ ref('int_hr_departments_current') }} as d  -- LKP_DEPARTMENT.Lookup condition
    on e.dept_code = d.dept_code
