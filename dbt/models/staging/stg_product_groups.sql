select
    group_code,
    group_name
from {{ ref('raw_product_groups') }}
