"""Rivi Insights — Streamlit dashboard for weekly hiring intelligence.

Main file path for deploy: streamlit_app.py
Run locally:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import html
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

st.set_page_config(
    page_title="Rivi Insights",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY = "#0B1220"
NAVY_SOFT = "#151D2E"
BLUE = "#2563EB"
BLUE_SOFT = "#E8EEF9"
FLAMINGO = "#F26622"
GREEN = "#22C55E"
RED = "#EF4444"
TEXT = "#0F172A"
MUTED = "#64748B"
BG = "#F4F6FA"
CARD = "#FFFFFF"

_SECRET_ENV_KEYS = (
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "GROQ_TEMPERATURE",
    "GROQ_MAX_TOKENS",
    "DATABASE_URL",
)

PAGES = (
    "AI Insights Dashboard",
    "Companies",
    "Job Intelligence",
)


def inject_styles() -> None:
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"]  {{
  font-family: "Plus Jakarta Sans", sans-serif;
}}

.stApp {{
  background: {BG};
}}

[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, {NAVY} 0%, #070B14 100%);
  border-right: 1px solid rgba(255,255,255,0.06);
  color: #E8EDF7;
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] strong {{
  color: #E8EDF7;
}}
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] small {{
  color: #94A3B8 !important;
}}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stRadio label {{
  color: #94A3B8 !important;
  font-size: 0.75rem !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
[data-testid="stSidebar"] [role="radiogroup"] label {{
  background: transparent !important;
  border-radius: 10px !important;
  padding: 0.55rem 0.75rem !important;
  margin-bottom: 0.2rem !important;
  color: #E8EDF7 !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
  background: rgba(255,255,255,0.06) !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"],
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
  background: rgba(37,99,235,0.28) !important;
  border: 1px solid rgba(37,99,235,0.45);
}}
[data-testid="stSidebar"] .stButton > button {{
  background: {BLUE};
  color: white !important;
  border: none;
  border-radius: 10px;
  font-weight: 600;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: #1D4ED8;
  color: white !important;
}}
/* Week selector: readable closed state */
[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
  background: {NAVY_SOFT} !important;
  border: 1px solid rgba(255,255,255,0.22) !important;
  color: #F8FAFC !important;
  min-height: 2.4rem;
}}
[data-testid="stSidebar"] div[data-baseweb="select"] svg {{
  fill: #F8FAFC !important;
  color: #F8FAFC !important;
}}
[data-testid="stSidebar"] div[data-baseweb="select"] span,
[data-testid="stSidebar"] div[data-baseweb="select"] div {{
  color: #F8FAFC !important;
}}
/* Dropdown list renders in a portal — keep dark text on white menu */
div[data-baseweb="popover"] li,
div[data-baseweb="menu"] li,
ul[role="listbox"] li,
div[data-baseweb="popover"] li span {{
  color: #0F172A !important;
}}
div[data-baseweb="popover"] li[aria-selected="true"],
ul[role="listbox"] li[aria-selected="true"] {{
  background: {BLUE_SOFT} !important;
  color: {BLUE} !important;
}}

.block-container {{
  padding-top: 1.25rem !important;
  padding-bottom: 2rem !important;
  max-width: 1400px;
}}

.rivi-brand {{
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin: 0.25rem 0 1.25rem 0;
}}
.rivi-mark {{
  width: 2rem;
  height: 2rem;
  border-radius: 8px;
  background: linear-gradient(135deg, {FLAMINGO}, #FF8A4C);
  box-shadow: 0 6px 16px rgba(242,102,34,0.35);
}}
.rivi-brand-text {{
  font-weight: 800;
  font-size: 1.15rem;
  letter-spacing: -0.02em;
  color: #fff !important;
  line-height: 1.15;
}}
.rivi-brand-sub {{
  font-size: 0.7rem;
  color: #94A3B8 !important;
  font-weight: 500;
}}

.rivi-nav-label {{
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748B !important;
  margin: 1rem 0 0.35rem 0;
  font-weight: 600;
}}

.rivi-api-card {{
  margin-top: 1rem;
  padding: 0.85rem 0.95rem;
  border-radius: 14px;
  background: {NAVY_SOFT};
  border: 1px solid rgba(255,255,255,0.08);
}}
.rivi-api-row {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}}
.rivi-dot {{
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  display: inline-block;
}}
.rivi-dot-ok {{
  background: {GREEN};
  box-shadow: 0 0 0 3px rgba(34,197,94,0.25);
}}
.rivi-dot-bad {{
  background: {RED};
  box-shadow: 0 0 0 3px rgba(239,68,68,0.25);
}}

.rivi-hero {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.1rem;
}}
.rivi-hero h1 {{
  margin: 0;
  font-size: 1.85rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: {TEXT};
}}
.rivi-hero p {{
  margin: 0.35rem 0 0 0;
  color: {MUTED};
  font-size: 0.95rem;
}}
.rivi-chip {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.8rem;
  border-radius: 999px;
  background: {BLUE_SOFT};
  color: {BLUE};
  font-size: 0.8rem;
  font-weight: 600;
  border: 1px solid rgba(37,99,235,0.15);
  white-space: nowrap;
}}

.rivi-kpi-grid {{
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0.25rem 0 1.25rem 0;
}}
@media (max-width: 1200px) {{
  .rivi-kpi-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
}}
@media (max-width: 700px) {{
  .rivi-kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
.rivi-kpi {{
  background: {CARD};
  border: 1px solid rgba(15,23,42,0.06);
  border-radius: 16px;
  padding: 1rem 1.05rem;
  box-shadow: 0 1px 2px rgba(15,23,42,0.04);
}}
.rivi-kpi .label {{
  color: {MUTED};
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}}
.rivi-kpi .value {{
  font-size: 1.65rem;
  font-weight: 800;
  color: {TEXT};
  letter-spacing: -0.03em;
  margin: 0.25rem 0;
  line-height: 1.1;
}}
.rivi-pill {{
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
}}
.pill-green {{ background: #DCFCE7; color: #166534; }}
.pill-blue {{ background: #DBEAFE; color: #1E40AF; }}
.pill-amber {{ background: #FEF3C7; color: #92400E; }}
.pill-red {{ background: #FEE2E2; color: #991B1B; }}

.rivi-panel {{
  background: {CARD};
  border: 1px solid rgba(15,23,42,0.06);
  border-radius: 18px;
  padding: 1.1rem 1.2rem;
  box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  margin-bottom: 1rem;
}}
.rivi-panel h3 {{
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  font-weight: 700;
  color: {TEXT};
}}
.rivi-panel-dark {{
  background: linear-gradient(160deg, #0F172A, #1E293B);
  color: #F8FAFC;
  border: none;
}}
.rivi-panel-dark h3, .rivi-panel-dark p, .rivi-panel-dark li {{
  color: #F8FAFC !important;
}}
.rivi-badge {{
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
.badge-green {{ background: #DCFCE7; color: #166534; }}
.badge-red {{ background: #FEE2E2; color: #991B1B; }}
.badge-blue {{ background: #DBEAFE; color: #1E40AF; }}

.rivi-panel-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}}
.rivi-panel-head h3 {{
  margin: 0;
}}
/* Native Streamlit bordered containers → match rivi-panel cards */
div[data-testid="stVerticalBlockBorderWrapper"] {{
  background: {CARD} !important;
  border: 1px solid rgba(15,23,42,0.06) !important;
  border-radius: 18px !important;
  box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  margin-bottom: 1rem;
  padding: 0.35rem 0.55rem 0.55rem 0.55rem;
}}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {{
  gap: 0.45rem;
}}
.rivi-section-title {{
  margin: 0.15rem 0 0.35rem 0;
  font-size: 1rem;
  font-weight: 700;
  color: {TEXT};
}}
.rivi-priority-list {{
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}}
.rivi-priority-item {{
  padding: 0.75rem 0.85rem;
  border-radius: 12px;
  background: #F8FAFC;
  border: 1px solid rgba(15,23,42,0.06);
}}
.rivi-priority-item .pr-name {{
  margin: 0 0 0.25rem 0;
  font-size: 0.92rem;
  font-weight: 700;
  color: {TEXT};
}}
.rivi-priority-item .pr-rationale {{
  margin: 0;
  font-size: 0.85rem;
  color: {MUTED};
  line-height: 1.45;
}}
.rivi-priority-item .pr-titles {{
  margin: 0.4rem 0 0 0;
  font-size: 0.78rem;
  color: #475569;
  font-style: italic;
  line-height: 1.35;
}}
.rivi-mover {{
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid rgba(15,23,42,0.06);
}}
.rivi-mover:last-child {{ border-bottom: none; }}
.rivi-avatar {{
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 8px;
  background: {BLUE_SOFT};
  color: {BLUE};
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 0.8rem;
  flex-shrink: 0;
}}
.rivi-mover-meta {{
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}}
.rivi-mover-meta strong {{
  font-size: 0.88rem;
  color: {TEXT};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.rivi-mover-meta span {{
  font-size: 0.78rem;
  color: {MUTED};
  font-weight: 600;
  white-space: nowrap;
}}
.rivi-spotlight {{
  background: linear-gradient(160deg, #0F172A, #1E293B);
  color: #F8FAFC;
  border-radius: 18px;
  padding: 1rem 1.2rem;
  margin: 0 0 1.1rem 0;
  border: 1px solid rgba(255,255,255,0.06);
}}
.rivi-spotlight .spot-label {{
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94A3B8;
  font-weight: 700;
  margin-bottom: 0.35rem;
}}
.rivi-spotlight p {{
  margin: 0;
  color: #E2E8F0;
  font-size: 0.95rem;
  line-height: 1.45;
}}

.rivi-alert {{
  border-radius: 14px;
  padding: 0.85rem 0.95rem;
  margin-bottom: 0.65rem;
  background: #F8FAFC;
  border: 1px solid rgba(15,23,42,0.06);
}}
.rivi-alert strong {{
  display: block;
  margin: 0.25rem 0;
  color: {TEXT};
}}
.rivi-alert p {{
  margin: 0;
  color: {MUTED};
  font-size: 0.85rem;
}}
.rivi-section-label {{
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 700;
  color: {MUTED};
  margin: 0.85rem 0 0.5rem 0;
}}
.rivi-section-label:first-of-type {{
  margin-top: 0.35rem;
}}
.rivi-callout-list {{
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  margin: 0 0 0.35rem 0;
}}
.rivi-callout-item {{
  padding: 0.7rem 0.8rem;
  border-radius: 12px;
  background: {BLUE_SOFT};
  border: 1px solid rgba(37,99,235,0.12);
}}
.rivi-callout-item .co-company {{
  font-size: 0.72rem;
  font-weight: 700;
  color: #1E40AF;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin: 0 0 0.2rem 0;
}}
.rivi-callout-item .co-title {{
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: {TEXT};
  line-height: 1.35;
}}
.rivi-callout-item .co-title a {{
  color: {TEXT};
  text-decoration: none;
}}
.rivi-callout-item .co-title a:hover {{
  color: {BLUE};
}}
.rivi-callout-item .co-why {{
  margin: 0.35rem 0 0 0;
  font-size: 0.8rem;
  color: {MUTED};
  line-height: 1.4;
}}
.rivi-risk-box {{
  margin-top: 0.25rem;
  padding: 0.75rem 0.85rem;
  border-radius: 12px;
  background: #FEF2F2;
  border: 1px solid rgba(239,68,68,0.18);
}}
.rivi-risk-box ul {{
  margin: 0.35rem 0 0 0;
  padding-left: 1.1rem;
  color: #7F1D1D;
  font-size: 0.85rem;
  line-height: 1.45;
}}
.rivi-risk-box li {{
  margin-bottom: 0.4rem;
}}
.rivi-risk-box li:last-child {{
  margin-bottom: 0;
}}
.rivi-empty-note {{
  color: {MUTED};
  margin: 0.4rem 0 0;
  font-size: 0.9rem;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def _apply_streamlit_secrets() -> None:
    import os

    try:
        secrets = st.secrets
    except Exception:
        return

    changed = False
    for key in _SECRET_ENV_KEYS:
        try:
            val = secrets[key]
        except Exception:
            continue
        if val is None:
            continue
        text = str(val).strip()
        if not text:
            continue
        if os.environ.get(key) != text:
            os.environ[key] = text
            changed = True
    if changed:
        from rivi.config import get_settings

        get_settings.cache_clear()


def runtime_settings():
    _apply_streamlit_secrets()
    from rivi.config import get_settings

    return get_settings()


def _db_path(settings) -> Path:
    url = settings.database_url or ""
    if url.startswith("sqlite:///"):
        rel = url.replace("sqlite:///", "", 1)
        p = Path(rel)
        if not p.is_absolute():
            p = _ROOT / p
        return p
    return _ROOT / "data" / "rivi.db"


def _groq_key_configured(settings) -> bool:
    return bool((settings.groq_api_key or "").strip())


def regenerate_week_insights(week_id: str) -> dict:
    from rivi.db import session_scope
    from rivi.insights.generate import generate_insights, regenerate_llm_only

    settings = runtime_settings()
    if not _groq_key_configured(settings):
        return {
            "llm_status": "failed",
            "error": "GROQ_API_KEY is not set. Add it under Streamlit Secrets (or .env locally).",
        }
    if not _db_path(settings).exists():
        return {
            "llm_status": "failed",
            "error": "No database found — cannot regenerate insights.",
        }

    with session_scope(settings) as session:
        try:
            return regenerate_llm_only(session, week_id, settings)
        except LookupError:
            return generate_insights(
                session, week_id=week_id, settings=settings, call_llm=True
            )


def _monitoring_label(*, career_page: str, skip: bool, eligible: bool) -> str:
    if skip:
        return "Skipped"
    if eligible:
        return "Eligible"
    if not (career_page or "").strip():
        return "Gap"
    return "Gap"


@st.cache_data(ttl=30)
def load_companies_from_db() -> tuple[list[dict], dict]:
    from sqlalchemy import select

    from rivi.db import session_scope
    from rivi.models import Company

    settings = runtime_settings()
    if not _db_path(settings).exists():
        rows = load_companies_csv()
        payload: list[dict] = []
        for r in rows:
            career = (r.get("career_page") or "").strip()
            skip = str(r.get("skip", "false")).lower() in {"true", "1", "yes"}
            eligible = bool(career) and not skip
            payload.append(
                {
                    "company_name": r.get("company_name") or "",
                    "category": r.get("category") or "",
                    "website": r.get("website") or "",
                    "career_page": career,
                    "career_page_status": r.get("career_page_status") or "",
                    "skip": skip,
                    "skip_reason": r.get("skip_reason") or "",
                    "eligible": eligible,
                    "monitoring": _monitoring_label(
                        career_page=career, skip=skip, eligible=eligible
                    ),
                }
            )
        return payload, {
            "total": len(payload),
            "eligible": sum(1 for r in payload if r["eligible"]),
            "skipped": sum(1 for r in payload if r["skip"]),
            "missing_career_page": sum(1 for r in payload if not r["career_page"]),
            "source": "csv",
        }

    with session_scope(settings) as session:
        all_rows = list(
            session.scalars(select(Company).order_by(Company.category, Company.name))
        )
        payload = [
            {
                "company_name": c.name,
                "category": c.category,
                "website": c.website,
                "career_page": c.career_page,
                "career_page_status": c.career_page_status,
                "skip": c.skip,
                "skip_reason": c.skip_reason or "",
                "eligible": c.is_eligible,
                "monitoring": _monitoring_label(
                    career_page=c.career_page,
                    skip=c.skip,
                    eligible=c.is_eligible,
                ),
            }
            for c in all_rows
        ]
        return payload, {
            "total": len(all_rows),
            "eligible": sum(1 for r in payload if r["eligible"]),
            "skipped": sum(1 for r in payload if r["skip"]),
            "missing_career_page": sum(1 for r in payload if not r["career_page"]),
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
    from rivi.db import session_scope
    from rivi.insights.generate import list_week_ids

    settings = runtime_settings()
    if not _db_path(settings).exists():
        return []
    with session_scope(settings) as session:
        return list_week_ids(session)


@st.cache_data(ttl=30)
def load_insight(week_id: str | None) -> dict | None:
    from rivi.db import session_scope
    from rivi.insights.generate import get_insight_payload

    settings = runtime_settings()
    if not _db_path(settings).exists():
        return None
    with session_scope(settings) as session:
        return get_insight_payload(session, week_id=week_id)


@st.cache_data(ttl=30)
def load_jobs_from_db() -> tuple[list[dict], dict]:
    from sqlalchemy import select

    from rivi.db import session_scope
    from rivi.models import Company, JobPosting

    settings = runtime_settings()
    db = _db_path(settings)
    meta = {"db_exists": db.exists(), "db_path": str(db)}
    if not db.exists():
        return [], meta

    rows: list[dict] = []
    with session_scope(settings) as session:
        companies = {
            c.id: {"name": c.name, "category": c.category or ""}
            for c in session.scalars(select(Company))
        }
        jobs = session.scalars(
            select(JobPosting)
            .where(JobPosting.in_scope.is_(True))
            .where(JobPosting.status == "open")
            .order_by(JobPosting.updated_at.desc())
        ).all()
        for j in jobs:
            co = companies.get(j.company_id) or {}
            rows.append(
                {
                    "company": co.get("name", ""),
                    "category": co.get("category", ""),
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
    from rivi.coverage import build_coverage_report
    from rivi.db import session_scope

    settings = runtime_settings()
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
            "unresolved": report.unresolved,
        }


def _companies_by_category(companies: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for c in companies:
        cat = (c.get("category") or "").strip() or "Uncategorized"
        grouped.setdefault(cat, []).append(c)
    return dict(sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def _esc(value: object) -> str:
    return html.escape(str(value or ""))


def _kpi_card(label: str, value: object, pill: str, pill_class: str) -> str:
    return (
        f'<div class="rivi-kpi">'
        f'<div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div>'
        f'<span class="rivi-pill {pill_class}">{_esc(pill)}</span>'
        f"</div>"
    )


def _job_table(rows: list[dict], *, key: str) -> None:
    if not rows:
        st.caption("No roles to show.")
        return
    display = []
    for j in rows:
        display.append(
            {
                "Company": j.get("company", ""),
                "Role": j.get("title", ""),
                "Function": j.get("function", ""),
                "Seniority": j.get("seniority_band") or j.get("seniority", ""),
                "Location": j.get("location", ""),
                "Category": j.get("category", ""),
                "Week": j.get("week", ""),
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


def _panel_html(title: str, body_html: str, *, badge: str | None = None, badge_class: str = "badge-blue") -> None:
    """Render a complete card in one markdown block (avoids Streamlit HTML splits)."""
    badge_html = (
        f'<span class="rivi-badge {badge_class}">{_esc(badge)}</span>' if badge else ""
    )
    st.markdown(
        f"""
<div class="rivi-panel">
  <div class="rivi-panel-head">
    <h3>{_esc(title)}</h3>
    {badge_html}
  </div>
  {body_html}
</div>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def _section(title: str, *, badge: str | None = None, badge_class: str = "badge-blue") -> Iterator[None]:
    """Card wrapper for mixed Streamlit widgets (charts, dataframes, inputs)."""
    with st.container(border=True):
        if badge:
            st.markdown(
                f'<div class="rivi-panel-head"><h3 class="rivi-section-title">{_esc(title)}</h3>'
                f'<span class="rivi-badge {badge_class}">{_esc(badge)}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<h3 class="rivi-section-title">{_esc(title)}</h3>',
                unsafe_allow_html=True,
            )
        yield


def _page_hero(title: str, subtitle: str, chip: str | None = None) -> None:
    chip_html = f'<div class="rivi-chip">{_esc(chip)}</div>' if chip else ""
    st.markdown(
        f"""
<div class="rivi-hero">
  <div>
    <h1>{_esc(title)}</h1>
    <p>{_esc(subtitle)}</p>
  </div>
  {chip_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def render_ai_insights_dashboard(
    *,
    insight: dict | None,
    jobs: list[dict],
    registry: dict,
    by_category: dict[str, list[dict]],
    week: str | None,
) -> None:
    structured = (insight or {}).get("structured") or {}
    summary = structured.get("summary") or {}
    priorities = (insight or {}).get("llm_priorities") or {}
    if isinstance(priorities, list):
        priorities = {"priority_companies": priorities}

    hot = structured.get("hottest_companies") or []
    lead = structured.get("leadership_pulse") or []
    new_rows = structured.get("new_openings") or []
    open_rows = structured.get("open_roles") or []
    table_rows = new_rows or open_rows or jobs[:40]

    leadership_jobs = [
        j
        for j in jobs
        if "+" in (j.get("seniority") or "").lower()
        or (j.get("seniority") or "").lower() in {"head", "director", "vp", "c-level"}
    ]

    status = (insight or {}).get("llm_status", "—")
    generated = ((insight or {}).get("generated_at") or "")[:19]
    model = (insight or {}).get("groq_model") or ""

    _page_hero(
        "AI Insights Dashboard",
        "Hiring signals and market intelligence across tracked startups.",
        chip=f"Week {week}" if week else "No week selected",
    )

    kpis = [
        _kpi_card("New roles", summary.get("new_count") or len(new_rows) or 0, "This week", "pill-green"),
        _kpi_card("Companies tracked", registry.get("eligible") or 0, "Eligible", "pill-blue"),
        _kpi_card(
            "Executive roles",
            summary.get("leadership_count") or len(lead) or len(leadership_jobs),
            "Head+",
            "pill-green",
        ),
        _kpi_card("In-scope openings", len(jobs), "Live", "pill-blue"),
        _kpi_card(
            "Companies OK",
            f"{summary.get('companies_ok') or 0}/{summary.get('companies_targeted') or 0}",
            "Latest run",
            "pill-amber",
        ),
        _kpi_card("Removed", summary.get("removed_count") or 0, "Cooling", "pill-red"),
    ]
    st.markdown(f'<div class="rivi-kpi-grid">{"".join(kpis)}</div>', unsafe_allow_html=True)

    brief = ((insight or {}).get("llm_brief") or "").strip()
    meta_bits = [f"LLM · {status}"]
    if model:
        meta_bits.append(model)
    if generated:
        meta_bits.append(generated)
    if brief:
        spot_body = _esc(brief)
    else:
        spot_body = "No AI brief yet — use Refresh Signals in the sidebar to generate one."
    st.markdown(
        f"""
<div class="rivi-spotlight">
  <div class="spot-label">Rivi AI Spotlight</div>
  <p style="opacity:0.7;font-size:0.78rem;margin:0 0 0.45rem 0">{_esc(" · ".join(meta_bits))}</p>
  <p>{spot_body}</p>
</div>
        """,
        unsafe_allow_html=True,
    )
    if (insight or {}).get("llm_status") == "failed":
        st.error("AI brief unavailable for this week. Structured lists below are still live.")

    left, right = st.columns([1.15, 1])
    with left:
        movers_items = []
        for h in hot[:5]:
            name = h.get("company") or "Unknown"
            roles = h.get("new_roles", 0)
            movers_items.append(
                f'<div class="rivi-mover">'
                f'<div class="rivi-avatar">{_esc(name[:1].upper())}</div>'
                f'<div class="rivi-mover-meta"><strong>{_esc(name)}</strong>'
                f"<span>+{roles}</span></div></div>"
            )
        movers_body = (
            "".join(movers_items)
            if movers_items
            else '<p class="rivi-empty-note">No movers this week.</p>'
        )
        _panel_html("Top movers", movers_body, badge="High activity", badge_class="badge-green")

        pcs = priorities.get("priority_companies") or []
        if pcs:
            priority_items = []
            for p in pcs:
                company = (p.get("company") or "").strip() or "Unknown"
                rationale = (p.get("rationale") or "").strip()
                titles = ", ".join(t for t in (p.get("cited_titles") or []) if t)
                titles_html = (
                    f'<p class="pr-titles">{_esc(titles)}</p>' if titles else ""
                )
                priority_items.append(
                    f'<div class="rivi-priority-item">'
                    f'<p class="pr-name">{_esc(company)}</p>'
                    f'<p class="pr-rationale">{_esc(rationale)}</p>'
                    f"{titles_html}"
                    f"</div>"
                )
            _panel_html(
                "Priority companies",
                f'<div class="rivi-priority-list">{"".join(priority_items)}</div>',
                badge=f"{len(pcs)} firms",
                badge_class="badge-blue",
            )
        else:
            _panel_html(
                "Priority companies",
                '<p class="rivi-empty-note">No priority companies in this pack.</p>',
            )

        mix = structured.get("function_mix") or {}
        if not mix:
            counts: dict[str, int] = {}
            for j in jobs:
                fn = j.get("function") or "Other"
                counts[fn] = counts.get(fn, 0) + 1
            mix = counts
        with _section("Function mix"):
            if mix:
                st.bar_chart(mix, height=220)
            else:
                st.caption("No function mix yet.")

    with right:
        callouts = priorities.get("role_callouts") or []
        risks = priorities.get("risk_notes") or []
        if isinstance(risks, str):
            risks = [risks]

        callout_html = []
        for c in callouts[:5]:
            title = (c.get("title") or "").strip()
            company = (c.get("company") or "").strip() or "Unknown"
            why = (c.get("why_it_matters") or "").strip()
            link = (c.get("job_url") or "").strip()
            if not title and not why:
                continue
            if link and title:
                title_html = f'<a href="{_esc(link)}" target="_blank" rel="noopener">{_esc(title)}</a>'
            else:
                title_html = _esc(title) if title else "Role highlight"
            why_html = f'<p class="co-why">{_esc(why)}</p>' if why else ""
            callout_html.append(
                f'<div class="rivi-callout-item">'
                f'<div class="co-company">{_esc(company)}</div>'
                f'<p class="co-title">{title_html}</p>'
                f"{why_html}"
                f"</div>"
            )

        risk_items = "".join(f"<li>{_esc(n)}</li>" for n in risks[:4] if str(n).strip())
        body_parts: list[str] = []
        if callout_html:
            body_parts.append(
                '<div class="rivi-section-label">Role callouts</div>'
                f'<div class="rivi-callout-list">{"".join(callout_html)}</div>'
            )
        if risk_items:
            body_parts.append(
                '<div class="rivi-section-label">Risk notes</div>'
                f'<div class="rivi-risk-box"><ul>{risk_items}</ul></div>'
            )
        if not body_parts:
            body_parts.append('<p class="rivi-empty-note">No alerts in this pack.</p>')

        _panel_html(
            "Signal alerts",
            "".join(body_parts),
            badge=f"{len(callout_html)} roles · {len(risks)} risks",
            badge_class="badge-blue",
        )

        sen_mix = structured.get("seniority_mix") or {}
        with _section("Seniority mix"):
            if sen_mix:
                st.bar_chart(sen_mix, height=180)
            else:
                st.caption("No seniority mix yet.")

        with _section("Category coverage"):
            if by_category:
                cat_chart = {k: len(v) for k, v in by_category.items()}
                st.bar_chart(cat_chart, height=160)
                st.caption(" · ".join(f"{cat}: {len(rows)}" for cat, rows in by_category.items()))
            else:
                st.caption("No categories loaded.")

    angles = priorities.get("outreach_angles") or []
    if angles:
        angle_items = []
        for a in angles:
            company = (a.get("company") or "").strip() or "Unknown"
            angle = (a.get("angle") or "").strip()
            angle_items.append(
                f'<div class="rivi-priority-item">'
                f'<p class="pr-name">{_esc(company)}</p>'
                f'<p class="pr-rationale">{_esc(angle)}</p>'
                f"</div>"
            )
        _panel_html(
            "Outreach angles",
            f'<div class="rivi-priority-list">{"".join(angle_items)}</div>',
            badge=f"{len(angles)}",
            badge_class="badge-green",
        )

    with _section(
        "Leadership pulse",
        badge=f"{len(lead)} roles" if lead else None,
        badge_class="badge-green",
    ):
        if lead:
            _job_table(lead, key="leadership")
        else:
            st.caption("No Head+ leadership signal this week.")

    feed_badge = f"{min(len(table_rows), 40)} roles"
    with _section("Role intelligence feed", badge=feed_badge, badge_class="badge-blue"):
        st.caption("Week deltas" if new_rows else "Open inventory")
        _job_table(table_rows[:40], key="dashboard_jobs")


def render_company_registry(
    companies: list[dict],
    coverage: dict | None,
) -> None:
    _page_hero(
        "Companies",
        "Registry health and career-page coverage across tracked firms.",
    )

    totals = coverage or {
        "eligible": sum(1 for c in companies if c.get("eligible")),
        "skipped": sum(1 for c in companies if c.get("skip")),
        "total": len(companies),
        "missing_career_page": sum(1 for c in companies if not (c.get("career_page") or "").strip()),
        "by_category": {},
    }

    kpis = [
        _kpi_card("Eligible", totals.get("eligible") or 0, "Active", "pill-green"),
        _kpi_card(
            "Missing careers",
            totals.get("missing_career_page") or 0,
            "Gap",
            "pill-red",
        ),
        _kpi_card("Skipped", totals.get("skipped") or 0, "Excluded", "pill-amber"),
        _kpi_card("Registry total", totals.get("total") or len(companies), "All rows", "pill-blue"),
    ]
    st.markdown(
        f'<div class="rivi-kpi-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">{"".join(kpis)}</div>',
        unsafe_allow_html=True,
    )

    by_cat_stats = totals.get("by_category") or {}
    if by_cat_stats:
        cats = list(by_cat_stats.items())
        cols = st.columns(min(len(cats), 4))
        for i, (cat, stats) in enumerate(cats):
            with cols[i % len(cols)]:
                eligible_n = stats.get("eligible", 0)
                total_n = stats.get("total", 0)
                st.markdown(
                    _kpi_card(cat, f"{eligible_n}/{total_n}", "Eligible / total", "pill-blue"),
                    unsafe_allow_html=True,
                )
    else:
        # CSV fallback: derive category counts from company list
        grouped = _companies_by_category(companies)
        if grouped:
            cols = st.columns(min(len(grouped), 4))
            for i, (cat, rows) in enumerate(grouped.items()):
                with cols[i % len(cols)]:
                    elig = sum(1 for r in rows if r.get("eligible"))
                    st.markdown(
                        _kpi_card(cat, f"{elig}/{len(rows)}", "Eligible / total", "pill-blue"),
                        unsafe_allow_html=True,
                    )

    if not companies:
        st.info("No companies in the registry.")
        return

    cat_opts = ["All"] + sorted(
        { (c.get("category") or "").strip() or "Uncategorized" for c in companies }
    )
    status_opts = ["Eligible", "Gaps", "Skipped", "All"]

    with _section("Registry browse"):
        f1, f2, f3 = st.columns([1.2, 1, 1.4])
        pick_cat = f1.selectbox("Category", cat_opts, index=0)
        pick_status = f2.selectbox("Monitoring status", status_opts, index=0)
        q = f3.text_input("Search company", "")

        view = companies
        if pick_cat != "All":
            view = [
                c
                for c in view
                if ((c.get("category") or "").strip() or "Uncategorized") == pick_cat
            ]
        if pick_status == "Eligible":
            view = [c for c in view if c.get("eligible")]
        elif pick_status == "Gaps":
            view = [c for c in view if not (c.get("career_page") or "").strip()]
        elif pick_status == "Skipped":
            view = [c for c in view if c.get("skip")]
        if q.strip():
            ql = q.strip().lower()
            view = [c for c in view if ql in (c.get("company_name") or "").lower()]

        display = [
            {
                "Company": r.get("company_name", ""),
                "Category": r.get("category", ""),
                "Monitoring": r.get("monitoring", ""),
                "Website": r.get("website", ""),
                "Career page": r.get("career_page", ""),
                "Notes": (r.get("skip_reason") or r.get("career_page_status") or ""),
            }
            for r in view
        ]
        st.caption(f"{len(display)} of {len(companies)} firms · {pick_status.lower()}")
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Website": st.column_config.LinkColumn("Website", display_text="Site"),
                "Career page": st.column_config.LinkColumn("Career page", display_text="Careers"),
            },
        )


def render_jobs(jobs: list[dict]) -> None:
    from rivi.hiring_summary import company_hiring_summaries

    _page_hero(
        "Job Intelligence",
        "Company hiring counts and in-scope open roles across tracked startups.",
    )
    if not jobs:
        st.info("No in-scope jobs to show.")
        return

    from rivi.classifier import IN_SCOPE_FUNCTIONS

    summaries = company_hiring_summaries(jobs)
    with _section("Company hiring counts", badge=f"{len(summaries)} firms", badge_class="badge-blue"):
        st.caption(
            "Per-company pulse from the latest scrape — headline shows the top senior "
            "openings, then non-IC (Manager+) and IC counts across in-scope functions."
        )
        hiring_display = [
            {
                "Company": r["company"],
                "Total": r["total"],
                "Non-IC": r["non_ic_count"],
                "IC": r["ic_count"],
                "Hiring summary": r["hiring_summary"],
                "Functions": r["functions_label"],
            }
            for r in summaries
        ]
        st.dataframe(
            hiring_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total": st.column_config.NumberColumn("Total", width="small"),
                "Non-IC": st.column_config.NumberColumn("Non-IC", width="small"),
                "IC": st.column_config.NumberColumn("IC", width="small"),
                "Hiring summary": st.column_config.TextColumn("Hiring summary", width="large"),
                "Functions": st.column_config.TextColumn("Functions", width="medium"),
            },
            key="company_hiring_counts",
        )

    fns = sorted(set(IN_SCOPE_FUNCTIONS) | {j["function"] for j in jobs if j["function"]})
    category_opts = sorted({j["category"] for j in jobs if j.get("category")})
    companies_opts = sorted({j["company"] for j in jobs if j["company"]})
    seniority_opts = sorted({j["seniority"] for j in jobs if j.get("seniority")})

    with _section("Browse openings"):
        f1, f2, f3, f4, f5 = st.columns([1.1, 1.2, 1, 1, 1.2])
        pick_cat = f1.multiselect("Function family / Category", category_opts)
        pick_co = f2.multiselect("Company", companies_opts)
        pick_fn = f3.multiselect("Function", fns)
        pick_sen = f4.multiselect("Seniority", seniority_opts)
        q = f5.text_input("Search title", "")

        view = jobs
        if pick_cat:
            view = [j for j in view if j.get("category") in pick_cat]
        if pick_co:
            view = [j for j in view if j["company"] in pick_co]
        if pick_fn:
            view = [j for j in view if j["function"] in pick_fn]
        if pick_sen:
            view = [j for j in view if j.get("seniority") in pick_sen]
        if q.strip():
            ql = q.strip().lower()
            view = [j for j in view if ql in (j["title"] or "").lower()]

        # When a single company is selected, surface its hiring summary above the role list
        if pick_co and len(pick_co) == 1:
            match = next((r for r in summaries if r["company"] == pick_co[0]), None)
            if match:
                st.info(match["hiring_summary"])

        st.caption(f"Displaying {len(view)} of {len(jobs)} in-scope open roles")
        _job_table(view, key="all_jobs")


def main() -> None:
    inject_styles()
    _apply_streamlit_secrets()
    settings = runtime_settings()

    companies, registry = load_companies_from_db()
    jobs, meta = load_jobs_from_db()
    weeks = load_week_ids()
    coverage = load_coverage()
    eligible_companies = [c for c in companies if c.get("eligible")]
    by_category = _companies_by_category(eligible_companies)

    with st.sidebar:
        st.markdown(
            """
<div class="rivi-brand">
  <div class="rivi-mark"></div>
  <div>
    <div class="rivi-brand-text">Rivi Insights</div>
    <div class="rivi-brand-sub">Hiring intelligence</div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="rivi-nav-label">Main</div>', unsafe_allow_html=True)
        page = st.radio(
            "Navigation",
            PAGES,
            index=0,
            label_visibility="collapsed",
        )

        st.markdown('<div class="rivi-nav-label">Week</div>', unsafe_allow_html=True)
        if weeks:
            week = st.selectbox("ISO week", weeks, index=0, label_visibility="collapsed")
        else:
            week = None
            st.caption("No insight weeks yet.")

        if week and st.button(
            "Refresh Signals",
            type="primary",
            disabled=not _groq_key_configured(settings),
            use_container_width=True,
            help="Re-call Groq for this week using the latest scrape run in the DB.",
        ):
            with st.spinner(f"Calling Groq for {week}…"):
                result = regenerate_week_insights(week)
            if result.get("llm_status") == "success":
                st.success(f"Fresh brief for {week}.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(result.get("error") or f"Groq status: {result.get('llm_status')}")

        if st.button("Reload data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown('<div class="rivi-nav-label">Active set</div>', unsafe_allow_html=True)
        st.caption(f"Eligible · {registry.get('eligible') or len(companies)}")
        st.caption(f"Open roles · {len(jobs)}")
        for cat, rows in by_category.items():
            st.caption(f"{cat} · {len(rows)}")

        ok = _groq_key_configured(settings)
        st.markdown(
            f"""
<div class="rivi-api-card">
  <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:#94A3B8;margin-bottom:0.35rem;font-weight:600">API status</div>
  <div class="rivi-api-row">
    <span class="rivi-dot {'rivi-dot-ok' if ok else 'rivi-dot-bad'}"></span>
    <strong>{'OK' if ok else 'Missing'}</strong>
    <span style="opacity:0.75">{'· Groq connected' if ok else '· add GROQ_API_KEY'}</span>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    if not meta.get("db_exists"):
        st.warning(
            "No `data/rivi.db` in this deploy — job listings and Groq insights need a "
            "committed/hosted database. Registry still loads from `data/companies.csv`."
        )

    insight = load_insight(week) if week else load_insight(None)

    if page == "AI Insights Dashboard":
        render_ai_insights_dashboard(
            insight=insight,
            jobs=jobs,
            registry=registry,
            by_category=by_category,
            week=week,
        )
    elif page == "Companies":
        render_company_registry(companies, coverage)
    else:
        render_jobs(jobs)


main()
