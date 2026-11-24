"""Pipeline state and logs.

- manifest/<doc_id>.json: what is currently in the index for each document
  (path, sha256, chunks, indexed_at). It drives change detection: only new or
  modified files are processed.
- logs/runs/*.jsonl and logs/documents/*.jsonl: append-only event logs, one file
  per run. dbt reads them to build the monitoring tables.

Locally everything lives under `state_dir`; on Azure the same files are kept in
the `pipeline-logs` blob container.
"""
from __future__ import annotations

import json
from pathlib import Path


class LocalStateStore:
    def __init__(self, root: str):
        self.root = Path(root)
        for d in ("manifest", "logs/runs", "logs/documents"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def load_manifest(self) -> dict:
        entries = (json.loads(f.read_text(encoding="utf-8")) for f in (self.root / "manifest").glob("*.json"))
        return {e["path"]: e for e in entries}

    def put_entry(self, entry: dict):
        f = self.root / "manifest" / f"{entry['doc_id']}.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(f)

    def delete_entry(self, doc_id: str):
        (self.root / "manifest" / f"{doc_id}.json").unlink(missing_ok=True)

    def append(self, kind: str, run_id: str, rows: list[dict]):
        if not rows:
            return
        with open(self.root / "logs" / kind / f"{run_id}.jsonl", "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, default=str) + "\n" for r in rows)

    def read(self, kind: str, run_id: str) -> list[dict]:
        f = self.root / "logs" / kind / f"{run_id}.jsonl"
        if not f.exists():
            return []
        return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]


class BlobStateStore:
    """Same layout in a blob container. One manifest blob per document so that
    documents processed in parallel by several function instances never
    overwrite each other's state."""

    def __init__(self, connection_string: str, container: str):
        from azure.storage.blob import ContainerClient

        self.c = ContainerClient.from_connection_string(connection_string, container)
        if not self.c.exists():
            self.c.create_container()

    def load_manifest(self) -> dict:
        out = {}
        for b in self.c.list_blobs(name_starts_with="manifest/"):
            e = json.loads(self.c.download_blob(b.name).readall())
            out[e["path"]] = e
        return out

    def put_entry(self, entry: dict):
        self.c.upload_blob(f"manifest/{entry['doc_id']}.json", json.dumps(entry, sort_keys=True), overwrite=True)

    def delete_entry(self, doc_id: str):
        self.c.delete_blob(f"manifest/{doc_id}.json", delete_snapshots="include")

    def append(self, kind: str, run_id: str, rows: list[dict]):
        if not rows:
            return
        b = self.c.get_blob_client(f"logs/{kind}/{run_id}.jsonl")
        if not b.exists():
            b.create_append_blob()
        b.append_block("".join(json.dumps(r, default=str) + "\n" for r in rows))

    def read(self, kind: str, run_id: str) -> list[dict]:
        b = self.c.get_blob_client(f"logs/{kind}/{run_id}.jsonl")
        if not b.exists():
            return []
        return [json.loads(line) for line in b.download_blob().readall().decode("utf-8").splitlines() if line]


def build_state(settings):
    if settings.backend == "azure":
        return BlobStateStore(settings.blob_connection_string, settings.logs_container)
    return LocalStateStore(settings.state_dir)
