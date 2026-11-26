{% snapshot snap_customers %}
{{
    config(
        target_schema='snapshots',
        unique_key='customer_id',
        strategy='timestamp',
        updated_at='updated_at'
    )
}}
-- Keeps the history of customer changes (SCD type 2), e.g. a customer moving country.
select * from {{ ref('stg_customers') }}
{% endsnapshot %}
