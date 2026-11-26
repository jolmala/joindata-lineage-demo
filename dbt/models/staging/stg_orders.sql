select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    upper(currency) as currency,
    status
from {{ ref('raw_orders') }}
