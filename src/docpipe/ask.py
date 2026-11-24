"""Question answering over the index, every answer quotes its sources."""
from __future__ import annotations

from dataclasses import dataclass

SYSTEM_PROMPT = (
    "Tu réponds uniquement à partir des extraits fournis. "
    "Chaque affirmation est suivie de sa source entre crochets, au format [fichier p.N]. "
    "Si les extraits ne contiennent pas la réponse, dis-le clairement."
)


@dataclass
class Answer:
    text: str
    sources: list[dict]


def _label(hit: dict) -> str:
    return f"[{hit['path']} p.{hit['page']}]"


def retrieve(question: str, index, embedder, k: int = 4) -> list[dict]:
    vec = embedder.embed([question])[0]
    return index.search(vec, k, query_text=question)


def answer(question: str, index, embedder, settings, k: int = 4) -> Answer:
    hits = retrieve(question, index, embedder, k)
    if not hits:
        return Answer("Aucun document indexé.", [])

    if settings.openai_endpoint and settings.openai_key:
        from openai import AzureOpenAI

        client = AzureOpenAI(azure_endpoint=settings.openai_endpoint, api_key=settings.openai_key, api_version="2024-10-21")
        context = "\n\n".join(f"{_label(h)}\n{h['text']}" for h in hits)
        resp = client.chat.completions.create(
            model=settings.openai_chat_deployment,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extraits :\n{context}\n\nQuestion : {question}"},
            ],
        )
        return Answer(resp.choices[0].message.content.strip(), hits)

    # without a language model: return the best passages with their reference
    best = hits[0]
    text = f"{best['text']}\n\n{_label(best)}"
    return Answer(text, hits)
