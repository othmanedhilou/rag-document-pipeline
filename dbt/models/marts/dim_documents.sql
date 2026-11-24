-- current state of every document ever seen
with ranked as (
    select
        *,
        row_number() over (partition by doc_id order by processed_at desc) as rn
    from {{ ref('stg_document_events') }}
),

last_indexed as (
    select doc_id, max(processed_at) as last_indexed_at
    from {{ ref('stg_document_events') }}
    where status = 'indexed'
    group by doc_id
)

select
    r.doc_id,
    r.path,
    r.extension,
    case
        when r.action = 'deleted' then 'deleted'
        when r.status = 'failed' then 'failed'
        else 'indexed'
    end                                                    as current_status,
    r.chunks                                               as chunks,
    r.pages                                                as pages,
    r.modified_at,
    li.last_indexed_at,
    date_diff('minute', r.modified_at, li.last_indexed_at) as indexing_lag_minutes,
    r.error                                                as last_error,
    r.run_id                                               as last_run_id
from ranked r
left join last_indexed li using (doc_id)
where r.rn = 1
