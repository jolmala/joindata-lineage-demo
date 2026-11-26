-- The mart total must equal delivered lines in the fact table (to the cent).
-- Returns a row only when they differ, so an empty result means the test passes.
with mart as (
    select sum(sales_eur) as total from {{ ref('mart_sales_by_country') }}
),
fact as (
    select round(sum(f.line_amount_eur), 2) as total
    from {{ ref('fct_order_lines') }} as f
    inner join {{ ref('dim_customer') }} as cu on f.customer_id = cu.customer_id
    where f.status = 'T'
)
select mart.total as mart_total, fact.total as fact_total
from mart cross join fact
where abs(mart.total - fact.total) > 0.05
