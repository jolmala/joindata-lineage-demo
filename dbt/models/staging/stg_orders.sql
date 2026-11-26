-- Order headers; currency upper-cased so it matches the rate table.
select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    upper(currency) as currency,
    status
from {{ source('erp', 'raw_orders') }}
