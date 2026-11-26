-- Products, as landed.
select
    product_id,
    product_name,
    group_code,
    unit
from {{ source('erp', 'raw_products') }}
