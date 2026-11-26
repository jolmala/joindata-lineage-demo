-- Department rows as delivered, all versions.
select
    upper(trim(dept_code)) as dept_code,
    dept_name,
    cast(cost_center as varchar) as cost_center,
    active_flag,
    cast(valid_from as date) as valid_from
from {{ source('hris', 'raw_hr_departments') }}
