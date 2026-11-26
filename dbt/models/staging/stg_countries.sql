select
    country_code,
    country_name,
    region
from {{ ref('raw_countries') }}
