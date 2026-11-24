-- a document cannot be indexed before the version it was built from existed
select *
from {{ ref('stg_document_events') }}
where status = 'indexed'
  and processed_at < modified_at
