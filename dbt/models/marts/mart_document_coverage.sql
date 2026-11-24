select
    extension,
    count(*) filter (where current_status = 'indexed')                 as documents_indexed,
    count(*) filter (where current_status = 'failed')                  as documents_failed,
    count(*) filter (where current_status = 'deleted')                 as documents_deleted,
    coalesce(sum(chunks) filter (where current_status = 'indexed'), 0) as chunks,
    round(avg(chunks) filter (where current_status = 'indexed'), 1)    as avg_chunks_per_document,
    count(*) filter (where current_status = 'indexed' and chunks = 0)  as indexed_without_chunks
from {{ ref('dim_documents') }}
group by extension
order by documents_indexed desc
