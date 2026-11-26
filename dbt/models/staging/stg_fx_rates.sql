select
    upper(currency) as currency,
    cast(rate_date as date) as rate_date,
    eur_per_unit
from {{ ref('raw_fx_rates') }}
