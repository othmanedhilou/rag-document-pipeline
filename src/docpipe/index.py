"""Vector index: a local NumPy store for development, Azure AI Search in the cloud.
Both expose the same three operations: upsert chunks, delete a document, search."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .chunking import Chunk


class LocalIndex:
    def __init__(self, directory: str, dim: int):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self.meta: list[dict] = []
        self.vectors = np.zeros((0, dim), dtype=np.float32)
        self._load()

    def _load(self):
        meta, vec = self.dir / "chunks.jsonl", self.dir / "vectors.npy"
        if meta.exists() and vec.exists():
            self.meta = [json.loads(line) for line in meta.read_text(encoding="utf-8").splitlines() if line]
            self.vectors = np.load(vec)
            if self.vectors.shape[1] != self.dim:
                raise ValueError(f"index built with dim {self.vectors.shape[1]}, embedder has {self.dim}; rebuild with --full")

    def save(self):
        with open(self.dir / "chunks.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(m, ensure_ascii=False) + "\n" for m in self.meta)
        np.save(self.dir / "vectors.npy", self.vectors)

    def delete_document(self, doc_id: str) -> int:
        keep = [i for i, m in enumerate(self.meta) if m["doc_id"] != doc_id]
        removed = len(self.meta) - len(keep)
        self.meta = [self.meta[i] for i in keep]
        self.vectors = self.vectors[keep] if keep else np.zeros((0, self.dim), dtype=np.float32)
        return removed

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray, doc_meta: dict) -> int:
        if not chunks:
            return 0
        self.delete_document(chunks[0].doc_id)
        self.meta += [{**asdict(c), **doc_meta} for c in chunks]
        self.vectors = np.vstack([self.vectors, vectors.astype(np.float32)])
        return len(chunks)

    def search(self, vector: np.ndarray, k: int, query_text: str | None = None) -> list[dict]:
        if not self.meta:
            return []
        scores = self.vectors @ vector.astype(np.float32)
        best = np.argsort(-scores)[:k]
        return [{**self.meta[i], "score": float(scores[i])} for i in best]

    def count(self) -> int:
        return len(self.meta)


class AzureSearchIndex:
    def __init__(self, endpoint: str, key: str, name: str, dim: int):
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient

        cred = AzureKeyCredential(key)
        self.dim = dim
        self.name = name
        self.admin = SearchIndexClient(endpoint, cred)
        self.client = SearchClient(endpoint, name, cred)

    def ensure(self):
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration,
            SearchableField,
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SimpleField,
            VectorSearch,
            VectorSearchProfile,
        )

        fields = [
            SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="path", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True),
            SimpleField(name="position", type=SearchFieldDataType.Int32),
            SimpleField(name="sha256", type=SearchFieldDataType.String),
            SimpleField(name="indexed_at", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
            SearchableField(name="text", type=SearchFieldDataType.String, analyzer_name="fr.microsoft"),
            SearchField(
                name="vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self.dim,
                vector_search_profile_name="hnsw",
            ),
        ]
        index = SearchIndex(
            name=self.name,
            fields=fields,
            vector_search=VectorSearch(
                algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
                profiles=[VectorSearchProfile(name="hnsw", algorithm_configuration_name="hnsw-algo")],
            ),
        )
        self.admin.create_or_update_index(index)

    def delete_document(self, doc_id: str) -> int:
        hits = list(self.client.search("*", filter=f"doc_id eq '{doc_id}'", select=["chunk_id"], top=1000))
        if hits:
            self.client.delete_documents([{"chunk_id": h["chunk_id"]} for h in hits])
        return len(hits)

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray, doc_meta: dict) -> int:
        if not chunks:
            return 0
        self.delete_document(chunks[0].doc_id)
        docs = [{**asdict(c), **doc_meta, "vector": v.tolist()} for c, v in zip(chunks, vectors, strict=True)]
        for i in range(0, len(docs), 500):
            self.client.upload_documents(docs[i:i + 500])
        return len(docs)

    def search(self, vector: np.ndarray, k: int, query_text: str | None = None) -> list[dict]:
        from azure.search.documents.models import VectorizedQuery

        results = self.client.search(
            search_text=query_text,          # hybrid: keyword + vector
            vector_queries=[VectorizedQuery(vector=vector.tolist(), k_nearest_neighbors=k, fields="vector")],
            select=["chunk_id", "doc_id", "path", "page", "position", "text"],
            top=k,
        )
        return [{**r, "score": r["@search.score"]} for r in results]

    def count(self) -> int:
        return self.client.get_document_count()

    def save(self):
        pass


def build_index(settings, dim: int):
    if settings.backend == "azure":
        idx = AzureSearchIndex(settings.search_endpoint, settings.search_key, settings.search_index, dim)
        idx.ensure()
        return idx
    return LocalIndex(f"{settings.state_dir}/index", dim)
