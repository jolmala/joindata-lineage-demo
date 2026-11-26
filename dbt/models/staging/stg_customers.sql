-- Customers, current state; updated_at drives the snapshot.
select
    customer_id,
    customer_name,
    country_code,
    email,
    cast(updated_at as timestamp) as updated_at
from {{ source('erp', 'raw_customers') }}
