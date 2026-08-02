"""Rivi Streamlit entrypoint for local demos and Streamlit Community Cloud.

Main file path for deploy: streamlit_app.py
Run locally:  streamlit run streamlit_app.py

Parity target: FastAPI Key Insights dashboard (hottest companies, leadership,
function/seniority mix, new openings, Groq brief + priorities).
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
    initial_sidebar_state="expanded",
)

RIVIERA_FLAMINGO = "#F26622"


def _db_path(settings) -> Path:
    url = settings.database_url or ""
    if url.startswith("sqlite:///"):
        rel = url.replace("sqlite:///", "", 1)
        p = Path(rel)
        if not p.is_absolute():
            p = _ROOT / p
        return p
    return _ROOT / "data" / "rivi.db"


@st.cache_data(ttl=30)
def load_companies_from_db() -> tuple[list[dict], dict]:
    """Eligible companies for the active monitoring set (+ optional skipped)."""
    from sqlalchemy import select

    from rivi.config import get_settings
    from rivi.db import session_scope
    from rivi.models import Company

    settings = get_settings()
    if not _db_path(settings).exists():
        # Fallback to CSV registry
        rows = load_companies_csv()
        eligible = [
            r
            for r in rows
            if (r.get("career_page") or "").strip()
            and str(r.get("skip", "false")).lower() not in {"true", "1", "yes"}
        ]
        return eligible, {
            "total": len(rows),
            "eligible": len(eligible),
            "skipped": len(rows) - len(eligible),
            "source": "csv",
        }

    with session_scope(settings) as session:
        all_rows = list(session.scalars(select(Company).order_by(Company.name)))
        eligible_rows = [c for c in all_rows if c.is_eligible]
        payload = [
            {
                "company_name": c.name,
                "category": c.category,
                "website": c.website,
                "career_page": c.career_page,
                "career_page_status": c.career_page_status,
                "skip": c.skip,
            }
            for c in eligible_rows
        ]
        return payload, {
            "total": len(all_rows),
            "eligible": len(eligible_rows),
            "skipped": sum(1 for c in all_rows if c.skip),
            "source": "db",
        }


def load_companies_csv() -> list[dict]:
    import csv

    path = _ROOT / "data" / "companies.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@st.cache_data(ttl=30)
def load_week_ids() -> list[str]:
    from rivi.config import get_settings
    from rivi.db import session_scope
    from rivi.insights.generate import list_week_ids

    settings = get_settings()
    if not _db_path(settings).exists():
        return []
    with session_scope(settings) as session:
        return list_week_ids(session)


@st.cache_data(ttl=30)
def load_insight(week_id: str | None) -> dict | None:
    from rivi.config import get_settings
    from rivi.db import session_scope
    from rivi.insights.generate import get_insight_payload

    settings = get_settings()
    if not _db_path(settings).exists():
        return None
    with session_scope(settings) as session:
        return get_insight_payload(session, week_id=week_id)


@st.cache_data(ttl=30)
def load_jobs_from_db() -> tuple[list[dict], dict]:
    from sqlalchemy import select

    from rivi.config import get_settings
    from rivi.db import session_scope
    from rivi.models import Company, JobPosting

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


@st.cache_data(ttl=30)
def load_coverage() -> dict | None:
    from rivi.config import get_settings
    from rivi.coverage import build_coverage_report
    from rivi.db import session_scope

    settings = get_settings()
    if not _db_path(settings).exists():
        return None
    with session_scope(settings) as session:
        report = build_coverage_report(session)
        return {
            "total": report.total,
            "eligible": report.eligible,
            "missing_career_page": report.missing_career_page,
            "skipped": report.skipped,
            "by_category": report.by_category,
        }


def _job_table(rows: list[dict], *, key: str) -> None:
    if not rows:
        st.caption("None.")
        return
    display = []
    for j in rows:
        display.append(
            {
                "Company": j.get("company", ""),
                "Title": j.get("title", ""),
                "Function": j.get("function", ""),
                "Seniority": j.get("seniority_band") or j.get("seniority", ""),
                "Location": j.get("location", ""),
                "Change": j.get("change_type", ""),
                "URL": j.get("job_url") or j.get("url") or "",
            }
        )
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("URL", display_text="Open"),
        },
        key=key,
    )


def _mix_chart(mix: dict, title: str) -> None:
    if not mix:
        st.caption("No data.")
        return
    st.caption(title)
    # Native chart — no pandas dependency required
    st.bar_chart(mix)


def render_key_insights(insight: dict) -> None:
    structured = insight.get("structured") or {}
    summary = structured.get("summary") or {}
    priorities = insight.get("llm_priorities") or {}
    if isinstance(priorities, list):
        priorities = {"priority_companies": priorities}

    week = insight.get("week_id") or summary.get("week_id") or ""
    st.markdown(f"### Week {week}")
    st.caption(
        f"LLM · **{insight.get('llm_status', '—')}**"
        + (f" · {insight.get('groq_model')}" if insight.get("groq_model") else "")
        + (f" · generated {insight.get('generated_at', '')[:19]}" if insight.get("generated_at") else "")
    )

    if insight.get("llm_status") == "failed":
        st.error(
            "AI brief unavailable for this week. Structured lists below are still live. "
            "Retry: `rivi generate-insights --week … --regenerate`"
        )
    if summary.get("run_status") == "partial":
        st.warning(
            f"Partial coverage — {summary.get('companies_failed') or 0} company scrape(s) failed."
        )

    # Stats strip (parity with FastAPI)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("New", summary.get("new_count") or 0)
    m2.metric("Updated", summary.get("updated_count") or 0)
    m3.metric("Removed", summary.get("removed_count") or 0)
    m4.metric("Leadership", summary.get("leadership_count") or 0)
    m5.metric(
        "Companies OK",
        f"{summary.get('companies_ok') or 0}/{summary.get('companies_targeted') or 0}",
    )

    st.divider()

    # Executive brief + Groq enablement
    st.subheader("Executive brief")
    if insight.get("llm_brief") and insight.get("llm_status") == "success":
        st.write(insight["llm_brief"])
    elif insight.get("llm_brief"):
        st.write(insight["llm_brief"])
        st.caption("Note: brief may be stale relative to llm_status.")
    else:
        st.info("No Groq brief for this week. Structured evidence follows.")

    pcs = priorities.get("priority_companies") or []
    if pcs:
        st.markdown("#### Priority companies")
        for p in pcs:
            titles = ", ".join(p.get("cited_titles") or [])
            st.markdown(
                f"**{p.get('company', '')}** — {p.get('rationale', '')}"
                + (f"  \n*{titles}*" if titles else "")
            )

    callouts = priorities.get("role_callouts") or []
    if callouts:
        st.markdown("#### Role callouts")
        for c in callouts:
            link = c.get("job_url") or ""
            title = c.get("title") or ""
            line = f"**{c.get('company', '')}** · {title}"
            if link:
                line = f"**{c.get('company', '')}** · [{title}]({link})"
            st.markdown(line)
            if c.get("why_it_matters"):
                st.caption(c["why_it_matters"])

    angles = priorities.get("outreach_angles") or []
    if angles:
        st.markdown("#### Outreach angles")
        for a in angles:
            st.markdown(f"**{a.get('company', '')}** — {a.get('angle', '')}")

    risks = priorities.get("risk_notes") or []
    if risks:
        st.markdown("#### Risk notes")
        for n in risks:
            st.markdown(f"- {n}")

    st.divider()

    # Hottest + mixes
    left, mid, right = st.columns(3)
    with left:
        st.subheader("Hottest companies")
        hot = structured.get("hottest_companies") or []
        if hot:
            hot_rows = [
                {"Company": h.get("company", ""), "New roles": h.get("new_roles", 0)}
                for h in hot
            ]
            st.dataframe(hot_rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No company rollup.")
    with mid:
        st.subheader("Function mix")
        _mix_chart(structured.get("function_mix") or {}, "New in-scope by function")
    with right:
        st.subheader("Seniority mix")
        _mix_chart(structured.get("seniority_mix") or {}, "New in-scope by seniority")

    st.divider()

    # New openings / open inventory
    new_rows = structured.get("new_openings") or []
    open_rows = structured.get("open_roles") or []
    st.subheader("New openings this week")
    if new_rows:
        st.caption(f"{len(new_rows)} in-scope new roles in this week's pack")
        _job_table(new_rows, key="new_openings")
    elif open_rows:
        st.warning(
            "No net-new deltas this week — showing current open in-scope inventory."
        )
        _job_table(open_rows, key="open_roles")
    else:
        st.caption("No new in-scope openings this week.")

    st.subheader("Leadership & executive pulse")
    lead = structured.get("leadership_pulse") or []
    if lead:
        st.caption(f"{len(lead)} Head+ / Director+ / VP+ / C-level signals")
        _job_table(lead, key="leadership")
    else:
        st.caption("No Head+ leadership signal this week.")

    removals = structured.get("removals") or []
    if removals:
        st.subheader("Removals / cooling")
        _job_table(removals, key="removals")

    gaps = structured.get("coverage_gaps") or {}
    if gaps:
        st.subheader("Coverage gaps")
        g1, g2, g3 = st.columns(3)
        g1.metric("Eligible", gaps.get("eligible") or 0)
        g2.metric("Missing career pages", gaps.get("missing_career_page_total") or 0)
        g3.metric("Skipped", gaps.get("skipped") or 0)
        fails = gaps.get("scrape_failures") or []
        if fails:
            st.caption("Scrape failures")
            st.dataframe(fails, use_container_width=True, hide_index=True)


def main() -> None:
    st.markdown(
        f"<h1 style='color:{RIVIERA_FLAMINGO};margin-bottom:0'>Rivi <span style='font-weight:500'>Key Insights</span></h1>"
        "<p style='opacity:0.8;margin-top:0.25rem'>Weekly hiring signal across tracked asset managers and banks</p>",
        unsafe_allow_html=True,
    )

    companies, registry = load_companies_from_db()
    jobs, meta = load_jobs_from_db()
    weeks = load_week_ids()
    coverage = load_coverage()

    with st.sidebar:
        st.markdown("### Week")
        if weeks:
            week = st.selectbox("Select week", weeks, index=0)
        else:
            week = None
            st.caption("No insight weeks yet.")
        st.divider()
        st.markdown("### Active set")
        st.metric("Eligible companies", registry.get("eligible") or len(companies))
        st.metric("In-scope open roles", len(jobs))
        skipped = registry.get("skipped") or 0
        if skipped:
            st.caption(f"{skipped} registry rows skipped (no career page / excluded)")
        if st.button("Refresh data"):
            st.cache_data.clear()
            st.rerun()

    if not meta.get("db_exists"):
        st.warning(
            "No `data/rivi.db` in this deploy — job listings and Groq insights need a "
            "committed/hosted database. Registry still loads from `data/companies.csv`."
        )

    insight = load_insight(week) if week else load_insight(None)

    tab_insights, tab_jobs, tab_companies, tab_coverage = st.tabs(
        ["Key Insights", "Jobs", "Companies", "Coverage"]
    )

    with tab_insights:
        if insight:
            render_key_insights(insight)
        else:
            st.info(
                "No insights yet. Run locally:\n\n"
                "`rivi scrape --all-eligible`\n\n"
                "`rivi generate-insights`"
            )
            st.caption("Or open the FastAPI UI at http://127.0.0.1:8000/ for the same dashboard.")

    with tab_jobs:
        if not jobs:
            st.write("No in-scope jobs to show.")
        else:
            from rivi.classifier import IN_SCOPE_FUNCTIONS

            # Always offer the full in-scope set (incl. IT), plus any extra labels present.
            fns = sorted(
                set(IN_SCOPE_FUNCTIONS)
                | {j["function"] for j in jobs if j["function"]}
            )
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
            st.caption(f"Showing {len(view)} of {len(jobs)} in-scope open roles")
            _job_table(view, key="all_jobs")

    with tab_companies:
        st.caption(
            f"Showing **{len(companies)} eligible** companies with career pages "
            f"(skipped/non-scrapeable rows hidden)."
        )
        if not companies:
            st.write("No eligible companies found.")
        else:
            st.dataframe(companies, use_container_width=True, hide_index=True)

    with tab_coverage:
        if not coverage:
            st.write("Coverage unavailable without database.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Eligible (active)", coverage["eligible"])
            c2.metric("Skipped", coverage["skipped"])
            c3.metric("Registry total", coverage["total"])
            st.caption(
                "Active monitoring uses eligible companies only. "
                "Skipped rows are missing a career page or were excluded."
            )
            by_cat = coverage.get("by_category") or {}
            if by_cat:
                rows = [
                    {
                        "Category": name,
                        "Eligible": stats.get("eligible", 0),
                        "Skipped / missing": stats.get("total", 0) - stats.get("eligible", 0),
                    }
                    for name, stats in by_cat.items()
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
    st.caption(
        "Full local UI (same data): http://127.0.0.1:8000/ · "
        "Scrape/Groq remain CLI-driven · Docs/streamlit-plan.md"
    )


main()
