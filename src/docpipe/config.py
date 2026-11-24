from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    backend: str = "local"                 # local | azure
    source_dir: str = "samples"
    state_dir: str = "state"
    embedder: str = "hashing"              # hashing | local | azure
    chunk_size: int = 900
    chunk_overlap: int = 150
    top_k: int = 4

    blob_connection_string: str = ""
    blob_container: str = "documents"
    logs_container: str = "pipeline-logs"
    search_endpoint: str = ""
    search_key: str = ""
    search_index: str = "documents"
    openai_endpoint: str = ""
    openai_key: str = ""
    openai_embedding_deployment: str = "text-embedding-3-small"
    openai_chat_deployment: str = "gpt-4o-mini"
    docintel_endpoint: str = ""
    docintel_key: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        s = cls()
        for field in s.__dataclass_fields__:
            value = os.environ.get(f"DOCPIPE_{field.upper()}")
            if value is not None:
                current = getattr(s, field)
                setattr(s, field, type(current)(value) if not isinstance(current, str) else value)
        return s
