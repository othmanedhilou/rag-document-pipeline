"""HTTP endpoints called by the Data Factory pipeline (and the /ask endpoint).

POST /api/plan      -> {run_id, started_at, seen, unchanged, to_process: [...], deleted: [...]}
POST /api/process   <- {run_id, path, size, modified, action}
POST /api/finalize  <- {run_id, started_at, seen, unchanged, deleted, trigger}
POST /api/ask       <- {question}
"""
import json
import logging
from datetime import datetime

import azure.functions as func

from docpipe.ask import answer
from docpipe.config import Settings
from docpipe.pipeline import Pipeline, now
from docpipe.sources import DocumentRef

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
_pipeline = None


def pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        s = Settings.from_env()
        s.backend = "azure"
        _pipeline = Pipeline(s)
    return _pipeline


def _json(body: dict, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body, default=str), status_code=status, mimetype="application/json")


@app.route(route="plan", methods=["POST"])
def plan(req: func.HttpRequest) -> func.HttpResponse:
    full = bool((req.get_json() if req.get_body() else {}).get("full", False))
    p = pipeline().plan(full=full)
    body = p.as_dict()
    body["started_at"] = now()
    logging.info("plan %s: %d to process, %d deleted", p.run_id, len(p.to_process), len(p.deleted))
    return _json(body)


@app.route(route="process", methods=["POST"])
def process(req: func.HttpRequest) -> func.HttpResponse:
    b = req.get_json()
    ref = DocumentRef(b["path"], int(b["size"]), datetime.fromisoformat(b["modified"]))
    event = pipeline().process(ref, b["run_id"], b.get("action", "new"), force=bool(b.get("full", False)))
    # a failed document returns 200 with status=failed: the run continues and the
    # failure is visible in the logs and in the dbt monitoring tables
    return _json(event)


@app.route(route="finalize", methods=["POST"])
def finalize(req: func.HttpRequest) -> func.HttpResponse:
    b = req.get_json()
    run = pipeline().finalize(
        b["run_id"], b.get("deleted", []), b["started_at"], b.get("trigger", "adf"),
        int(b.get("seen", 0)), int(b.get("unchanged", 0)),
    )
    return _json(run, 500 if run["status"] == "failed" else 200)


@app.route(route="ask", methods=["POST"])
def ask(req: func.HttpRequest) -> func.HttpResponse:
    q = (req.get_json() or {}).get("question", "").strip()
    if not q:
        return _json({"error": "question is required"}, 400)
    p = pipeline()
    res = answer(q, p.index, p.embedder, p.s)
    return _json({
        "answer": res.text,
        "sources": [{"path": h["path"], "page": h["page"], "score": h["score"]} for h in res.sources],
    })
