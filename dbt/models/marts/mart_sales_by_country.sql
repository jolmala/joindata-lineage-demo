-- Answers: "List countries by sales, and where were the most drills sold, in units and euros?"
select
    c.country_code,
    c.country_name,
    c.region,
    count(distinct f.order_id) as delivered_orders,
    sum(f.quantity) as units,
    round(sum(f.line_amount_eur), 2) as sales_eur,
    sum(case when p.group_code = 'POR' then f.quantity else 0 end) as drill_units,
    round(sum(case when p.group_code = 'POR' then f.line_amount_eur else 0 end), 2) as drill_sales_eur
from {{ ref('fct_order_lines') }} as f
inner join {{ ref('dim_customer') }} as cu on f.customer_id = cu.customer_id
inner join {{ ref('dim_country') }} as c on cu.country_code = c.country_code
left join {{ ref('dim_product') }} as p on f.product_id = p.product_id
where f.status = 'T'
group by c.country_code, c.country_name, c.region
