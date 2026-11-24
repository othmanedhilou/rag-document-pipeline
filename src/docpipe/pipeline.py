"""Incremental indexing.

plan     list the source, compare with the manifest -> new / changed / deleted
process  one document: extract, chunk, embed, upsert into the index
finalize remove deleted documents from the index and write the run record

`sync` chains the three steps in one process. On Azure, Data Factory calls the
same three steps through the Function App and runs `process` in parallel.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .chunking import chunk_pages
from .config import Settings
from .embeddings import build_embedder
from .extract import extract
from .index import build_index
from .sources import BlobSource, DocumentRef, LocalSource, sha256
from .state import build_state

log = logging.getLogger("docpipe")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Plan:
    run_id: str
    seen: int
    new: list[DocumentRef] = field(default_factory=list)
    changed: list[DocumentRef] = field(default_factory=list)
    unchanged: int = 0
    deleted: list[dict] = field(default_factory=list)

    @property
    def to_process(self) -> list[DocumentRef]:
        return self.new + self.changed

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "seen": self.seen,
            "unchanged": self.unchanged,
            "to_process": [
                {"path": r.path, "size": r.size, "modified": r.modified.isoformat(), "action": action}
                for action, refs in (("new", self.new), ("changed", self.changed))
                for r in refs
            ],
            "deleted": [{"path": d["path"], "doc_id": d["doc_id"]} for d in self.deleted],
        }


class Pipeline:
    def __init__(self, settings: Settings, source=None, index=None, embedder=None, state=None):
        self.s = settings
        self.source = source or (
            BlobSource(settings.blob_connection_string, settings.blob_container)
            if settings.backend == "azure" else LocalSource(settings.source_dir)
        )
        self.embedder = embedder or build_embedder(settings)
        self.index = index or build_index(settings, self.embedder.dim)
        self.state = state or build_state(settings)

    # ---------------------------------------------------------------- plan
    def plan(self, full: bool = False) -> Plan:
        manifest = self.state.load_manifest()
        refs = self.source.list()
        p = Plan(run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6], seen=len(refs))
        for ref in refs:
            entry = manifest.get(ref.path)
            if entry is None:
                p.new.append(ref)
            elif full or entry["size"] != ref.size or entry["modified"] < ref.modified.isoformat():
                p.changed.append(ref)
            else:
                p.unchanged += 1
        current = {r.path for r in refs}
        p.deleted = [e for path, e in manifest.items() if path not in current]
        return p

    # ------------------------------------------------------------- process
    def process(self, ref: DocumentRef, run_id: str, action: str, force: bool = False) -> dict:
        started = time.perf_counter()
        event = {
            "run_id": run_id, "doc_id": ref.doc_id, "path": ref.path, "extension": ref.extension,
            "action": action, "size_bytes": ref.size, "modified_at": ref.modified.isoformat(),
            "processed_at": now(), "pages": 0, "chunks": 0, "chars": 0, "error": None,
        }
        try:
            data = self.source.read(ref.path)
            digest = sha256(data)
            event["sha256"] = digest
            previous = self.state.load_manifest().get(ref.path) if action == "changed" else None
            if previous and previous["sha256"] == digest and not force:
                # file touched but content identical: refresh metadata, skip embeddings
                self.state.put_entry({**previous, "size": ref.size, "modified": ref.modified.isoformat()})
                event.update(status="unchanged", chunks=previous["chunks"])
                return self._log(event, started)

            pages = extract(data, ref.extension, (self.s.docintel_endpoint, self.s.docintel_key))
            chunks = chunk_pages(pages, ref.doc_id, ref.path, self.s.chunk_size, self.s.chunk_overlap)
            vectors = self.embedder.embed([c.text for c in chunks])
            indexed_at = now()
            self.index.upsert(chunks, vectors, {"sha256": digest, "indexed_at": indexed_at})
            self.index.save()
            self.state.put_entry({
                "doc_id": ref.doc_id, "path": ref.path, "sha256": digest, "size": ref.size,
                "modified": ref.modified.isoformat(), "chunks": len(chunks), "pages": len(pages),
                "indexed_at": indexed_at,
            })
            event.update(status="indexed", pages=len(pages), chunks=len(chunks), chars=sum(len(c.text) for c in chunks))
        except Exception as e:  # one bad file must not stop the run
            log.exception("failed %s", ref.path)
            event.update(status="failed", error=f"{type(e).__name__}: {e}"[:500])
        return self._log(event, started)

    def _log(self, event: dict, started: float) -> dict:
        event["duration_ms"] = int((time.perf_counter() - started) * 1000)
        self.state.append("documents", event["run_id"], [event])
        log.info("%-9s %-8s %s (%d chunks)", event["action"], event["status"], event["path"], event["chunks"])
        return event

    # ------------------------------------------------------------ finalize
    def finalize(self, run_id: str, deleted: list[dict], started_at: str, trigger: str, seen: int, unchanged: int) -> dict:
        removed_events = []
        for d in deleted:
            n = self.index.delete_document(d["doc_id"])
            self.state.delete_entry(d["doc_id"])
            removed_events.append({
                "run_id": run_id, "doc_id": d["doc_id"], "path": d["path"], "action": "deleted",
                "status": "removed", "chunks": n, "processed_at": now(), "duration_ms": 0, "error": None,
            })
        self.index.save()
        self.state.append("documents", run_id, removed_events)

        events = [e for e in self.state.read("documents", run_id) if e["action"] != "deleted"]
        run = {
            "run_id": run_id,
            "trigger": trigger,
            "started_at": started_at,
            "finished_at": now(),
            "docs_seen": seen,
            "docs_new": sum(e["action"] == "new" for e in events),
            "docs_changed": sum(e["action"] == "changed" and e["status"] == "indexed" for e in events),
            "docs_unchanged": unchanged + sum(e["status"] == "unchanged" for e in events),
            "docs_deleted": len(deleted),
            "docs_failed": sum(e["status"] == "failed" for e in events),
            "chunks_written": sum(e["chunks"] for e in events if e["status"] == "indexed"),
            "index_size": self.index.count(),
            "embedder": self.s.embedder,
        }
        run["status"] = "failed" if run["docs_failed"] and run["docs_failed"] == len(events) else (
            "partial" if run["docs_failed"] else "success"
        )
        self.state.append("runs", run_id, [run])
        return run

    # ---------------------------------------------------------------- sync
    def sync(self, trigger: str = "manual", full: bool = False) -> dict:
        started_at = now()
        p = self.plan(full=full)
        log.info("run %s: %d seen, %d new, %d changed, %d deleted", p.run_id, p.seen, len(p.new), len(p.changed), len(p.deleted))
        for ref in p.new:
            self.process(ref, p.run_id, "new")
        for ref in p.changed:
            self.process(ref, p.run_id, "changed", force=full)
        return self.finalize(p.run_id, p.deleted, started_at, trigger, p.seen, p.unchanged)
