"""Where documents come from: a local folder or an Azure Blob container."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED = {".pdf", ".txt", ".md"}


@dataclass(frozen=True)
class DocumentRef:
    path: str            # relative path, also used as document id
    size: int
    modified: datetime

    @property
    def doc_id(self) -> str:
        return hashlib.sha1(self.path.encode("utf-8")).hexdigest()[:16]

    @property
    def extension(self) -> str:
        return Path(self.path).suffix.lower()


class LocalSource:
    def __init__(self, root: str):
        self.root = Path(root)

    def list(self) -> list[DocumentRef]:
        refs = []
        for f in sorted(self.root.rglob("*")):
            if f.is_file() and f.suffix.lower() in SUPPORTED:
                st = f.stat()
                refs.append(DocumentRef(
                    f.relative_to(self.root).as_posix(),
                    st.st_size,
                    datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                ))
        return refs

    def read(self, path: str) -> bytes:
        return (self.root / path).read_bytes()


class BlobSource:
    def __init__(self, connection_string: str, container: str):
        from azure.storage.blob import ContainerClient

        self.container = ContainerClient.from_connection_string(connection_string, container)

    def list(self) -> list[DocumentRef]:
        return [
            DocumentRef(b.name, b.size, b.last_modified)
            for b in self.container.list_blobs()
            if Path(b.name).suffix.lower() in SUPPORTED
        ]

    def read(self, path: str) -> bytes:
        return self.container.download_blob(path).readall()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
