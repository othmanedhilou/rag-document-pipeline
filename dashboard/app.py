"""Monitoring dashboard + question box.

    streamlit run dashboard/app.py

Reads the dbt tables from state/monitoring.duckdb (run `dbt build` first).
"""
import sys
from pathlib import Path

import duckdb
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from docpipe.ask import answer
from docpipe.config import Settings
from docpipe.pipeline import Pipeline

DB = ROOT / "state" / "monitoring.duckdb"

st.set_page_config(page_title="Document pipeline", layout="wide")
st.title("Pipeline documentaire")

if not DB.exists():
    st.warning("Run `docpipe sync` then `dbt build --profiles-dir .` in the dbt folder.")
    st.stop()

con = duckdb.connect(str(DB), read_only=True)
fresh = con.sql("select * from mart_index_freshness").df().iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Documents indexés", int(fresh.documents_indexed))
c2.metric("Chunks", int(fresh.chunks_indexed))
c3.metric("En échec", int(fresh.documents_failed))
c4.metric("Dernier succès (min)", int(fresh.minutes_since_last_success))
c5.metric("Délai moyen d'indexation (min)", fresh.avg_indexing_lag_minutes)
if bool(fresh.is_stale):
    st.error("Index obsolète : aucun run réussi récemment.")

left, right = st.columns(2)
with left:
    st.subheader("Runs")
    runs = con.sql("""
        select started_at, trigger, status, docs_new, docs_changed, docs_deleted, docs_failed,
               chunks_written, index_size, duration_seconds
        from fct_runs order by started_at desc limit 20
    """).df()
    st.dataframe(runs, hide_index=True, use_container_width=True)
    st.line_chart(runs.sort_values("started_at"), x="started_at", y="index_size")
with right:
    st.subheader("Couverture par type")
    st.dataframe(con.sql("select * from mart_document_coverage").df(), hide_index=True, use_container_width=True)
    st.subheader("Documents")
    st.dataframe(
        con.sql("select path, current_status, chunks, pages, last_indexed_at, last_error from dim_documents order by path").df(),
        hide_index=True, use_container_width=True,
    )

st.divider()
st.subheader("Poser une question")


@st.cache_resource
def get_pipeline():
    s = Settings.from_env()
    s.source_dir = str(ROOT / "samples")
    s.state_dir = str(ROOT / "state")
    return Pipeline(s)


q = st.text_input("Question")
if q:
    p = get_pipeline()
    res = answer(q, p.index, p.embedder, p.s)
    st.write(res.text)
    st.caption("Sources : " + ", ".join(f"{h['path']} p.{h['page']} ({h['score']:.2f})" for h in res.sources))
