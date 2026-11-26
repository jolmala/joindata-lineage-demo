-- Run after `dbt build`, e.g. with the DuckDB CLI:  duckdb joindata_orders.duckdb < queries/top_drill_countries.sql
select country_name, drill_units, drill_sales_eur, sales_eur
from main.mart_sales_by_country
order by drill_sales_eur desc;
