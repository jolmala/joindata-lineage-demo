-- Customers for reporting; e-mail (personal data) is left out on purpose.
select
    customer_id,
    customer_name,
    country_code
from {{ ref('stg_customers') }}
