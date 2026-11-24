select
    run_id,
    doc_id,
    path,
    coalesce(extension, lower(regexp_extract(path, '(\.[A-Za-z0-9]+)$', 1))) as extension,
    action,
    status,
    try_cast(size_bytes as bigint)            as size_bytes,
    try_cast(modified_at as timestamptz)      as modified_at,
    cast(processed_at as timestamptz)         as processed_at,
    coalesce(pages, 0)                        as pages,
    coalesce(chunks, 0)                       as chunks,
    coalesce(chars, 0)                        as chars,
    duration_ms,
    error
from read_json_auto('{{ var("logs_path") }}/documents/*.jsonl', format = 'newline_delimited', union_by_name = true)
