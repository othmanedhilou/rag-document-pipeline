"""
    docpipe sync [--full]          index new and modified documents, drop deleted ones
    docpipe ask "question"         answer from the index with sources
    docpipe status                 last runs
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .ask import answer
from .config import Settings
from .pipeline import Pipeline


def main(argv=None):
    p = argparse.ArgumentParser(prog="docpipe")
    p.add_argument("--source", help="documents folder (local backend)")
    p.add_argument("--state", help="state folder (local backend)")
    p.add_argument("--embedder", choices=["hashing", "local", "azure"])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--full", action="store_true", help="re-embed everything")
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("-k", type=int)
    sub.add_parser("status")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    if args.source:
        settings.source_dir = args.source
    if args.state:
        settings.state_dir = args.state
    if args.embedder:
        settings.embedder = args.embedder

    if args.cmd == "status":
        runs = sorted((Path(settings.state_dir) / "logs" / "runs").glob("*.jsonl"))[-10:]
        for f in runs:
            r = json.loads(f.read_text(encoding="utf-8").splitlines()[-1])
            print(f"{r['run_id']}  {r['status']:<8} new={r['docs_new']} changed={r['docs_changed']} "
                  f"deleted={r['docs_deleted']} failed={r['docs_failed']} index={r['index_size']}")
        return

    pipe = Pipeline(settings)
    if args.cmd == "sync":
        print(json.dumps(pipe.sync(full=args.full), indent=2))
    elif args.cmd == "ask":
        res = answer(args.question, pipe.index, pipe.embedder, settings, args.k or settings.top_k)
        print(res.text)
        print("\nSources :")
        for h in res.sources:
            print(f"  {h['score']:.3f}  {h['path']} p.{h['page']}")


if __name__ == "__main__":
    main()
