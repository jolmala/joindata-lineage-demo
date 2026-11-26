-- Order lines with the order's attributes and the line amount converted to euros.
-- Currency rule: the rate of the order date (decided by finance; see the mart description).
select
    l.line_id,
    l.order_id,
    o.order_date,
    o.customer_id,
    o.status,
    l.product_id,
    l.quantity,
    o.currency,
    l.line_amount,
    fx.eur_per_unit,
    round(l.line_amount * fx.eur_per_unit, 2) as line_amount_eur
from {{ ref('stg_order_lines') }} as l
inner join {{ ref('stg_orders') }} as o on l.order_id = o.order_id
left join {{ ref('stg_fx_rates') }} as fx
    on o.currency = fx.currency
    and o.order_date = fx.rate_date
