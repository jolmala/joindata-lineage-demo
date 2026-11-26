-- Order lines; line_amount is in the order currency, excluding VAT.
select
    line_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    quantity * unit_price as line_amount
from {{ source('erp', 'raw_order_lines') }}
