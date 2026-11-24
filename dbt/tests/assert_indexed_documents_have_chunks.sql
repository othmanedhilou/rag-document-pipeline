select *
from {{ ref('dim_documents') }}
where current_status = 'indexed'
  and chunks = 0
