select
    run_id,
    trigger,
    cast(started_at as timestamptz)  as started_at,
    cast(finished_at as timestamptz) as finished_at,
    date_diff('second', cast(started_at as timestamptz), cast(finished_at as timestamptz)) as duration_seconds,
    docs_seen,
    docs_new,
    docs_changed,
    docs_unchanged,
    docs_deleted,
    docs_failed,
    chunks_written,
    index_size,
    embedder,
    status
from read_json_auto('{{ var("logs_path") }}/runs/*.jsonl', format = 'newline_delimited', union_by_name = true)
