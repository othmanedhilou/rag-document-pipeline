-- single row read by the dashboard
with runs as (
    select * from {{ ref('fct_runs') }}
),

docs as (
    select * from {{ ref('dim_documents') }}
)

select
    (select max(finished_at) from runs)                                    as last_run_at,
    (select max(finished_at) from runs where status = 'success')           as last_success_at,
    date_diff('minute', (select max(finished_at) from runs where status <> 'failed'), now())
                                                                           as minutes_since_last_success,
    (select count(*) from docs where current_status = 'indexed')           as documents_indexed,
    (select coalesce(sum(chunks), 0) from docs where current_status = 'indexed') as chunks_indexed,
    (select count(*) from docs where current_status = 'failed')            as documents_failed,
    (select round(avg(indexing_lag_minutes), 1) from docs where current_status = 'indexed') as avg_indexing_lag_minutes,
    (select max(indexing_lag_minutes) from docs where current_status = 'indexed')           as max_indexing_lag_minutes,
    date_diff('minute', (select max(finished_at) from runs where status <> 'failed'), now())
        > {{ var('stale_after_minutes') }}                                 as is_stale
