"""Rivi Streamlit entrypoint for local demos and Streamlit Community Cloud.

Main file path for deploy: streamlit_app.py
Run locally:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure src/ layout package is importable (Cloud + local without editable install)
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

st.set_page_config(
    page_title="Rivi · Key Insights",
    page_icon="🟠",
    layout="wide",
)

RIVIERA_FLAMINGO = "#F26622"


def _load_settings():
    from rivi.config import get_settings

    return get_settings()


def _db_path(settings) -> Path:
    # Default sqlite:///./data/rivi.db → resolve against repo root
    url = settings.database_url or ""
    if url.startswith("sqlite:///"):
        rel = url.replace("sqlite:///", "", 1)
        p = Path(rel)
        if not p.is_absolute():
            p = _ROOT / p
        return p
    return _ROOT / "data" / "rivi.db"


@st.cache_data(ttl=60)
def load_companies_csv() -> list[dict]:
    import csv

    path = _ROOT / "data" / "companies.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@st.cache_data(ttl=60)
def load_jobs_from_db() -> tuple[list[dict], dict]:
    """Return (job rows, meta). Empty jobs if DB missing."""
    from sqlalchemy import select

    from rivi.db import session_scope
    from rivi.models import Company, JobPosting
    from rivi.config import get_settings

    settings = get_settings()
    db = _db_path(settings)
    meta = {"db_exists": db.exists(), "db_path": str(db)}
    if not db.exists():
        return [], meta

    rows: list[dict] = []
    with session_scope(settings) as session:
        companies = {c.id: c.name for c in session.scalars(select(Company))}
        jobs = session.scalars(
            select(JobPosting)
            .where(JobPosting.in_scope.is_(True))
            .where(JobPosting.status == "open")
            .order_by(JobPosting.updated_at.desc())
        ).all()
        for j in jobs:
            rows.append(
                {
                    "company": companies.get(j.company_id, ""),
                    "title": j.title,
                    "function": j.function,
                    "seniority": j.seniority_band,
                    "location": j.location or "",
                    "week": j.last_seen_week or "",
                    "url": j.job_url or "",
                }
            )
    meta["job_count"] = len(rows)
    return rows, meta


@st.cache_data(ttl=60)
def load_insight() -> dict | None:
    from rivi.config import get_settings
    from rivi.db import session_scope
    from rivi.insights.generate import get_insight_payload

    settings = get_settings()
    if not _db_path(settings).exists():
        return None
    with session_scope(settings) as session:
        return get_insight_payload(session)


def main() -> None:
    st.markdown(
        f"<h1 style='color:{RIVIERA_FLAMINGO};margin-bottom:0'>Rivi</h1>"
        "<p style='opacity:0.8;margin-top:0.25rem'>Career-page monitoring · Key Insights</p>",
        unsafe_allow_html=True,
    )

    companies = load_companies_csv()
    jobs, meta = load_jobs_from_db()
    insight = load_insight()

    c1, c2, c3 = st.columns(3)
    c1.metric("Companies (registry)", len(companies))
    c2.metric("In-scope open roles", len(jobs))
    eligible = sum(
        1
        for r in companies
        if (r.get("career_page") or "").strip()
        and str(r.get("skip", "false")).lower() not in {"true", "1", "yes"}
    )
    c3.metric("Eligible career pages", eligible)

    if not meta.get("db_exists"):
        st.warning(
            "No `data/rivi.db` in this deploy — job listings and Groq insights need a local scrape "
            "or a committed/hosted database. Registry below still loads from `data/companies.csv`."
        )

    tab_insights, tab_jobs, tab_companies = st.tabs(["Key Insights", "Jobs", "Companies"])

    with tab_insights:
        if insight and insight.get("llm_status") == "failed":
            st.error(
                "Groq insights failed for this week (often token-limit). "
                "Structured job data below is still valid — retry locally with "
                "`rivi generate-insights --week … --regenerate`."
            )
        if insight and insight.get("llm_brief") and insight.get("llm_status") == "success":
            st.subheader(f"Week {insight.get('week_id', '')}")
            st.caption(f"LLM status: {insight.get('llm_status', '—')}")
            st.write(insight["llm_brief"])
        elif insight and insight.get("llm_brief"):
            st.subheader(f"Week {insight.get('week_id', '')}")
            st.caption(f"LLM status: {insight.get('llm_status', '—')} (stale brief may be shown)")
            st.write(insight["llm_brief"])
        elif insight:
            st.subheader(f"Week {insight.get('week_id', '')}")
            st.info(
                f"Structured insights present (llm_status={insight.get('llm_status')}), "
                "but no Groq executive brief yet."
            )
            structured = insight.get("structured") or {}
            summary = structured.get("summary") or {}
            if summary:
                st.json(summary)
        else:
            st.info(
                "No weekly insights in the database yet. "
                "Run locally: `rivi scrape --all-eligible` then `rivi generate-insights`."
            )

    with tab_jobs:
        if not jobs:
            st.write("No in-scope jobs to show.")
        else:
            fns = sorted({j["function"] for j in jobs if j["function"]})
            companies_opts = sorted({j["company"] for j in jobs if j["company"]})
            f1, f2, f3 = st.columns(3)
            pick_co = f1.multiselect("Company", companies_opts)
            pick_fn = f2.multiselect("Function", fns)
            q = f3.text_input("Search title", "")
            view = jobs
            if pick_co:
                view = [j for j in view if j["company"] in pick_co]
            if pick_fn:
                view = [j for j in view if j["function"] in pick_fn]
            if q.strip():
                ql = q.strip().lower()
                view = [j for j in view if ql in (j["title"] or "").lower()]
            st.caption(f"Showing {len(view)} of {len(jobs)} in-scope roles")
            st.dataframe(view, use_container_width=True, hide_index=True)

    with tab_companies:
        if not companies:
            st.write("No companies.csv found.")
        else:
            st.dataframe(companies, use_container_width=True, hide_index=True)

    st.divider()
    st.caption(
        "Scrape & Groq stay on the CLI / scheduler. "
        "See Docs/streamlit-plan.md for the full hosting roadmap."
    )


main()
