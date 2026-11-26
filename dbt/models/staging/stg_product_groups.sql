-- Product groups, as landed.
select
    group_code,
    group_name
from {{ source('erp', 'raw_product_groups') }}
