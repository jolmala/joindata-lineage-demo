-- Countries, as landed.
select
    country_code,
    country_name,
    region
from {{ source('erp', 'raw_countries') }}
