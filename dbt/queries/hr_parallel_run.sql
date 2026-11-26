-- Active headcount by department, new model next to the legacy table (run after dbt build).
select
    n.dept_name,
    n.active_dbt,
    coalesce(o.active_legacy, 0) as active_legacy
from (
    select dept_name, count(*) as active_dbt from dim_employee where is_active = 'Y' group by dept_name
) as n
left join (
    select dept_name, count(*) as active_legacy from legacy_dim_employee where is_active = 'Y' group by dept_name
) as o on n.dept_name = o.dept_name
order by n.active_dbt desc, n.dept_name
