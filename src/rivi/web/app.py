from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from rivi.config import Settings, get_settings
from rivi.coverage import build_coverage_report
from rivi.db import get_session_factory
from rivi.diff import LEADERSHIP_BANDS
from rivi.export import build_week_pack, export_week_pack
from rivi.insights.deep_dive import company_deep_dive
from rivi.insights.generate import (
    get_insight_payload,
    list_week_ids,
    regenerate_llm_only,
)
from rivi.models import Company, JobPosting, ScrapeRun, WeeklyInsight

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
security = HTTPBasic(auto_error=False)


def _auth_required(settings: Settings) -> bool:
    return bool(settings.basic_auth_user and settings.basic_auth_password)


def require_basic_auth(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
):
    settings = get_settings()
    if not _auth_required(settings):
        return None
    # Always require when configured (for non-localhost exposure)
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(credentials.username, settings.basic_auth_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.basic_auth_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def create_app(*, enable_scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Rivi", description="Career-page monitoring Key Insights")
    settings = get_settings()

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    scheduler = None
    if enable_scheduler:
        from rivi.scheduler import start_scheduler

        @app.on_event("startup")
        def _start() -> None:
            nonlocal scheduler
            scheduler = start_scheduler(settings)

        @app.on_event("shutdown")
        def _stop() -> None:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    # ── JSON API ──────────────────────────────────────────────

    @app.get("/api/insights/latest")
    def api_insights_latest(_user=Depends(require_basic_auth)) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            payload = get_insight_payload(session)
            if payload is None:
                raise HTTPException(404, "No insights yet")
            return payload

    @app.get("/api/insights/{week_id}")
    def api_insights_week(week_id: str, _user=Depends(require_basic_auth)) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            payload = get_insight_payload(session, week_id)
            if payload is None:
                raise HTTPException(404, f"No insights for {week_id}")
            return payload

    @app.post("/api/insights/{week_id}/regenerate")
    def api_regenerate(week_id: str, _user=Depends(require_basic_auth)) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            try:
                result = regenerate_llm_only(session, week_id, settings)
            except LookupError as e:
                raise HTTPException(404, str(e)) from e
            return result

    @app.get("/api/export/{week_id}")
    def api_export(
        week_id: str,
        format: str = Query("json", pattern="^(json|csv)$"),
        _user=Depends(require_basic_auth),
    ):
        factory = get_session_factory(settings)
        with factory() as session:
            try:
                if format == "csv":
                    json_path, csv_path = export_week_pack(
                        session, week_id, settings=settings
                    )
                    data = csv_path.read_text(encoding="utf-8")
                    return Response(
                        content=data,
                        media_type="text/csv",
                        headers={
                            "Content-Disposition": f'attachment; filename="{csv_path.name}"'
                        },
                    )
                pack = build_week_pack(session, week_id)
                return JSONResponse(pack)
            except LookupError as e:
                raise HTTPException(404, str(e)) from e

    @app.post("/api/companies/{company_id}/deep-dive")
    def api_deep_dive(company_id: int, _user=Depends(require_basic_auth)) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise HTTPException(404, "Company not found")
            return company_deep_dive(session, company.name, settings=settings)

    @app.get("/api/jobs")
    def api_jobs(
        week: Optional[str] = None,
        in_scope: bool = True,
        seniority: Optional[str] = None,
        status: str = "open",
        limit: int = Query(200, le=1000),
        _user=Depends(require_basic_auth),
    ) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            q = select(JobPosting)
            if in_scope:
                q = q.where(JobPosting.in_scope.is_(True))
            if status:
                q = q.where(JobPosting.status == status)
            if seniority:
                q = q.where(JobPosting.seniority_band == seniority)
            if week:
                q = q.where(JobPosting.last_seen_week == week)
            jobs = list(session.scalars(q.order_by(JobPosting.updated_at.desc()).limit(limit)))
            names = {c.id: c.name for c in session.scalars(select(Company))}
            return {
                "count": len(jobs),
                "jobs": [
                    {
                        "id": j.id,
                        "company": names.get(j.company_id, ""),
                        "title": j.title,
                        "location": j.location,
                        "function": j.function,
                        "seniority_band": j.seniority_band,
                        "job_url": j.job_url,
                        "first_seen_week": j.first_seen_week,
                        "last_seen_week": j.last_seen_week,
                        "status": j.status,
                        "in_scope": j.in_scope,
                    }
                    for j in jobs
                ],
            }

    @app.get("/api/companies")
    def api_companies(_user=Depends(require_basic_auth)) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            rows = list(session.scalars(select(Company).order_by(Company.name)))
            return {
                "count": len(rows),
                "companies": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "category": c.category,
                        "website": c.website,
                        "career_page": c.career_page,
                        "career_page_status": c.career_page_status,
                        "skip": c.skip,
                        "eligible": c.is_eligible,
                    }
                    for c in rows
                ],
            }

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: int, _user=Depends(require_basic_auth)) -> dict[str, Any]:
        factory = get_session_factory(settings)
        with factory() as session:
            run = session.get(ScrapeRun, run_id)
            if run is None:
                raise HTTPException(404, "Run not found")
            return {
                "id": run.id,
                "week_id": run.week_id,
                "status": run.status,
                "trigger": run.trigger,
                "started_at": run.started_at.isoformat() if run.started_at else "",
                "finished_at": run.finished_at.isoformat() if run.finished_at else "",
                "stats": json.loads(run.stats_json or "{}"),
            }

    # ── HTML UI ───────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def home(
        request: Request,
        week: Optional[str] = None,
        _user=Depends(require_basic_auth),
    ):
        factory = get_session_factory(settings)
        with factory() as session:
            weeks = list_week_ids(session)
            payload = get_insight_payload(session, week)
            if payload is None and weeks and week is None:
                payload = get_insight_payload(session, weeks[0])
            return templates.TemplateResponse(
                request,
                "insights.html",
                {
                    "insight": payload,
                    "weeks": weeks,
                    "selected_week": (payload or {}).get("week_id") or week,
                    "leadership_bands": sorted(LEADERSHIP_BANDS),
                },
            )

    @app.get("/weeks", response_class=HTMLResponse)
    def weeks_page(request: Request, _user=Depends(require_basic_auth)):
        factory = get_session_factory(settings)
        with factory() as session:
            weeks = list_week_ids(session)
            rows = []
            for w in weeks:
                insight = session.scalar(
                    select(WeeklyInsight)
                    .where(WeeklyInsight.week_id == w)
                    .order_by(WeeklyInsight.id.desc())
                    .limit(1)
                )
                rows.append(
                    {
                        "week_id": w,
                        "llm_status": insight.llm_status if insight else "",
                        "generated_at": insight.generated_at.isoformat()
                        if insight and insight.generated_at
                        else "",
                    }
                )
            return templates.TemplateResponse(
                request,
                "weeks.html",
                {"weeks": weeks, "week_rows": rows, "selected_week": weeks[0] if weeks else None},
            )

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(
        request: Request,
        week: Optional[str] = None,
        seniority: Optional[str] = None,
        _user=Depends(require_basic_auth),
    ):
        factory = get_session_factory(settings)
        with factory() as session:
            q = (
                select(JobPosting)
                .where(JobPosting.in_scope.is_(True), JobPosting.status == "open")
                .order_by(JobPosting.first_seen_week.desc(), JobPosting.title)
                .limit(500)
            )
            if week:
                q = q.where(JobPosting.last_seen_week == week)
            if seniority:
                q = q.where(JobPosting.seniority_band == seniority)
            jobs = list(session.scalars(q))
            names = {c.id: c.name for c in session.scalars(select(Company))}
            rows = [
                {
                    "company": names.get(j.company_id, ""),
                    "title": j.title,
                    "location": j.location,
                    "function": j.function,
                    "seniority_band": j.seniority_band,
                    "job_url": j.job_url,
                    "first_seen_week": j.first_seen_week,
                }
                for j in jobs
            ]
            weeks = list_week_ids(session)
            return templates.TemplateResponse(
                request,
                "jobs.html",
                {"jobs": rows, "weeks": weeks, "selected_week": week, "seniority": seniority},
            )

    @app.get("/companies", response_class=HTMLResponse)
    def companies_page(request: Request, _user=Depends(require_basic_auth)):
        factory = get_session_factory(settings)
        with factory() as session:
            rows = list(
                session.scalars(select(Company).order_by(Company.category, Company.name))
            )
            return templates.TemplateResponse(
                request,
                "companies.html",
                {"companies": rows},
            )

    @app.get("/companies/{company_id}", response_class=HTMLResponse)
    def company_detail(
        request: Request,
        company_id: int,
        _user=Depends(require_basic_auth),
    ):
        factory = get_session_factory(settings)
        with factory() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise HTTPException(404, "Company not found")
            jobs = list(
                session.scalars(
                    select(JobPosting)
                    .where(
                        JobPosting.company_id == company_id,
                        JobPosting.in_scope.is_(True),
                    )
                    .order_by(JobPosting.status, JobPosting.title)
                )
            )
            return templates.TemplateResponse(
                request,
                "company_detail.html",
                {"company": company, "jobs": jobs, "deep_dive": None},
            )

    @app.post("/companies/{company_id}/deep-dive", response_class=HTMLResponse)
    def company_deep_dive_page(
        request: Request,
        company_id: int,
        _user=Depends(require_basic_auth),
    ):
        factory = get_session_factory(settings)
        with factory() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise HTTPException(404, "Company not found")
            result = company_deep_dive(session, company.name, settings=settings)
            jobs = list(
                session.scalars(
                    select(JobPosting)
                    .where(
                        JobPosting.company_id == company_id,
                        JobPosting.in_scope.is_(True),
                    )
                    .order_by(JobPosting.status, JobPosting.title)
                )
            )
            return templates.TemplateResponse(
                request,
                "company_detail.html",
                {"company": company, "jobs": jobs, "deep_dive": result},
            )

    @app.get("/coverage", response_class=HTMLResponse)
    def coverage_page(request: Request, _user=Depends(require_basic_auth)):
        factory = get_session_factory(settings)
        with factory() as session:
            report = build_coverage_report(session)
            return templates.TemplateResponse(
                request,
                "coverage.html",
                {"report": report},
            )

    @app.get("/insights", response_class=RedirectResponse)
    def insights_redirect():
        return RedirectResponse("/", status_code=302)

    return app


app = create_app()
