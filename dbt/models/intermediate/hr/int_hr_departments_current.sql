-- One row per department: the active row with the latest valid_from.
-- Replaces LKP_DEPARTMENT (Lookup Source Filter ACTIVE_FLAG = 'Y', policy "Use Last Value"); see D3.
select dept_code, dept_name, cost_center
from (
    select
        dept_code,
        dept_name,
        cost_center,
        row_number() over (partition by dept_code order by valid_from desc) as row_no
    from {{ ref('stg_hr_departments') }}
    where active_flag = 'Y'
) as d
where row_no = 1
