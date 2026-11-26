select
    product_id,
    product_name,
    group_code,
    unit
from {{ ref('raw_products') }}
