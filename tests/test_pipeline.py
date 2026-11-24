import os
import time

import pytest

from docpipe.ask import answer
from docpipe.config import Settings
from docpipe.embeddings import HashingEmbedder
from docpipe.pipeline import Pipeline

DOCS = {
    "teletravail.md": "# Teletravail\n\nLe teletravail est limite a deux jours par semaine.\n\n"
                      "Une indemnite de 30 euros par mois est versee.",
    "incidents.md": "# Incidents\n\nUn incident P1 est pris en charge en 15 minutes.\n\n"
                    "Un incident P2 est pris en charge en 1 heure.",
    "frais.txt": "Le plafond pour un repas d'affaires est de 35 euros par personne.",
}


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "docs"
    src.mkdir()
    for name, text in DOCS.items():
        (src / name).write_text(text, encoding="utf-8")
    s = Settings(source_dir=str(src), state_dir=str(tmp_path / "state"), chunk_size=200, chunk_overlap=30)
    return s, src


def test_first_sync_indexes_everything(env):
    s, _ = env
    run = Pipeline(s).sync()
    assert run["docs_new"] == 3
    assert run["status"] == "success"
    assert run["index_size"] == run["chunks_written"] > 0


def test_second_sync_is_a_no_op(env):
    s, _ = env
    Pipeline(s).sync()
    run = Pipeline(s).sync()
    assert (run["docs_new"], run["docs_changed"], run["docs_unchanged"], run["chunks_written"]) == (0, 0, 3, 0)


def test_modified_deleted_and_touched_files(env):
    s, src = env
    Pipeline(s).sync()
    time.sleep(0.05)
    (src / "frais.txt").write_text("Le plafond pour un repas d'affaires est de 40 euros.", encoding="utf-8")
    (src / "incidents.md").unlink()
    touched = src / "teletravail.md"
    os.utime(touched, (time.time() + 5, time.time() + 5))   # newer mtime, same content

    p = Pipeline(s)
    run = p.sync()
    assert run["docs_changed"] == 1
    assert run["docs_deleted"] == 1
    assert run["docs_unchanged"] == 1
    assert {h["path"] for h in p.index.meta} == {"frais.txt", "teletravail.md"}

    # the touched file must not be planned again on the next run
    assert Pipeline(s).plan().to_process == []


def test_broken_file_does_not_stop_the_run(env):
    s, src = env
    (src / "broken.pdf").write_bytes(b"not a pdf")
    run = Pipeline(s).sync()
    assert run["docs_failed"] == 1
    assert run["status"] == "partial"
    assert run["docs_new"] == 4


def test_answer_cites_the_right_document(env):
    s, _ = env
    p = Pipeline(s)
    p.sync()
    res = answer("combien de jours de teletravail par semaine", p.index, p.embedder, s, k=2)
    assert res.sources[0]["path"] == "teletravail.md"
    assert "[teletravail.md p.1]" in res.text


def test_full_rebuild_reembeds(env):
    s, _ = env
    Pipeline(s).sync()
    run = Pipeline(s).sync(full=True)
    assert run["docs_changed"] == 3
    assert run["chunks_written"] == run["index_size"]


def test_hashing_embedder_is_normalized_and_accent_insensitive():
    e = HashingEmbedder()
    a, b = e.embed(["Télétravail à domicile", "teletravail a domicile"])
    assert abs((a @ a) - 1) < 1e-5
    assert (a @ b) > 0.99
