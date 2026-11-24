from __future__ import annotations

import hashlib
import re
import unicodedata

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


class HashingEmbedder:
    """Bag of words + word bigrams hashed into a fixed vector. No model to
    download, deterministic, good enough for keyword-heavy questions and for tests."""

    dim = 1024

    def _vec(self, text: str) -> np.ndarray:
        tokens = [t for t in _TOKEN.findall(_normalize(text)) if len(t) > 2]
        feats = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        v = np.zeros(self.dim, dtype=np.float32)
        for f in feats:
            h = int.from_bytes(hashlib.md5(f.encode()).digest()[:4], "little")
            v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)


class LocalModelEmbedder:
    def __init__(self, model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, batch_size=32).astype(np.float32)


class AzureOpenAIEmbedder:
    dim = 1536

    def __init__(self, endpoint: str, key: str, deployment: str):
        from openai import AzureOpenAI

        self.client = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version="2024-10-21")
        self.deployment = deployment

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 64):
            resp = self.client.embeddings.create(model=self.deployment, input=texts[i:i + 64])
            out.extend(d.embedding for d in resp.data)
        return np.array(out, dtype=np.float32)


def build_embedder(settings):
    if settings.embedder == "azure":
        return AzureOpenAIEmbedder(settings.openai_endpoint, settings.openai_key, settings.openai_embedding_deployment)
    if settings.embedder == "local":
        return LocalModelEmbedder()
    return HashingEmbedder()
