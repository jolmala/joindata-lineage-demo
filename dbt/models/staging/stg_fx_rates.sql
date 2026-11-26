-- Daily rates: euros for one unit of the currency.
select
    upper(currency) as currency,
    cast(rate_date as date) as rate_date,
    eur_per_unit
from {{ source('erp', 'raw_fx_rates') }}
