select
    customer_id,
    customer_name,
    country_code,
    email,
    cast(updated_at as timestamp) as updated_at
from {{ ref('raw_customers') }}
