-- Employees, standardised. Birth date and e-mail are left out on purpose (not in the legacy target).
select
    emp_id,
    trim(first_name) as first_name,
    trim(last_name) as last_name,
    upper(trim(dept_code)) as dept_code,
    job_code,
    employment_type,
    cast(hire_date as date) as hire_date,
    cast(term_date as date) as term_date,
    cast(fte as decimal(4, 2)) as fte
from {{ source('hris', 'raw_hr_employees') }}
