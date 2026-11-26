-- Products with their group, for slicing sales by product group.
select
    p.product_id,
    p.product_name,
    p.unit,
    p.group_code,
    g.group_name
from {{ ref('stg_products') }} as p
left join {{ ref('stg_product_groups') }} as g on p.group_code = g.group_code
