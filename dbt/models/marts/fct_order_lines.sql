-- Incremental fact table. On a full refresh every line is loaded; on later runs only
-- orders from the last 7 days are reloaded, which also picks up late status changes.
{{
    config(
        materialized='incremental',
        unique_key='line_id',
        incremental_strategy='delete+insert'
    )
}}

select
    line_id,
    order_id,
    order_date,
    customer_id,
    product_id,
    status,
    quantity,
    currency,
    line_amount,
    line_amount_eur
from {{ ref('int_order_lines_eur') }}
{% if is_incremental() %}
where order_date >= (select max(order_date) - interval 7 day from {{ this }})
{% endif %}
