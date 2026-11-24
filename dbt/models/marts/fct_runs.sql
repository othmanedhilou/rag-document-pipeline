select
    *,
    case when docs_new + docs_changed + docs_failed = 0 then 0
         else round(100.0 * docs_failed / (docs_new + docs_changed + docs_failed), 1)
    end as failure_rate_pct,
    lag(index_size) over (order by started_at) as previous_index_size
from {{ ref('stg_runs') }}
