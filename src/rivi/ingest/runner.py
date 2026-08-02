from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from rivi.classifier import Classification
from rivi.config import Settings, get_settings
from rivi.diff import compute_diffs, metadata_changed
from rivi.ingest.engine import classify_jobs, identity_key, scrape_career_page
from rivi.models import Company, CompanyRun, JobPosting, JobSnapshot, ScrapeRun, utcnow
from rivi.week import current_week_id

logger = logging.getLogger("rivi.scrape")


def _eligible_query(
    session: Session,
    company_name: str | None = None,
    category: str | None = None,
):
    q = select(Company).where(Company.skip.is_(False)).where(Company.career_page != "")
    if company_name:
        q = q.where(Company.name == company_name)
    if category:
        q = q.where(Company.category == category)
    return q.order_by(Company.category, Company.name)


def upsert_job(
    session: Session,
    company: Company,
    job,
    classification: Classification,
    week_id: str,
    scrape_run_id: int,
) -> tuple[JobPosting, str]:
    """Upsert a posting. Returns (row, change_type) where change_type is
    new | updated | unchanged | reopened.
    """
    key = identity_key(company.id, job)
    existing = session.scalar(
        select(JobPosting).where(
            JobPosting.company_id == company.id,
            JobPosting.identity_key == key,
        )
    )
    now = utcnow()
    if existing is None:
        row = JobPosting(
            company_id=company.id,
            external_id=job.external_id or "",
            identity_key=key,
            title=job.title,
            location=job.location or "",
            job_url=job.job_url or "",
            function=classification.function,
            seniority_band=classification.seniority_band,
            in_scope=classification.in_scope,
            match_evidence=classification.match_evidence,
            first_seen_week=week_id,
            last_seen_week=week_id,
            status="open",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        session.add(
            JobSnapshot(
                scrape_run_id=scrape_run_id,
                job_posting_id=row.id,
                raw_payload_ref=json.dumps({"title": job.title, "url": job.job_url})[:2000],
            )
        )
        return row, "new"

    was_removed = existing.status == "removed"
    changed = metadata_changed(
        existing,
        job.title or "",
        job.location if job.location is not None else existing.location,
        job.job_url or "",
    )

    existing.title = job.title or existing.title
    existing.location = job.location if job.location is not None else existing.location
    existing.job_url = job.job_url or existing.job_url
    existing.external_id = job.external_id or existing.external_id
    existing.function = classification.function
    existing.seniority_band = classification.seniority_band
    existing.in_scope = classification.in_scope
    existing.match_evidence = classification.match_evidence
    existing.last_seen_week = week_id
    existing.status = "open"
    existing.updated_at = now

    if was_removed:
        existing.first_seen_week = week_id
        change = "reopened"
    elif changed:
        change = "updated"
    else:
        change = "unchanged"

    session.add(
        JobSnapshot(
            scrape_run_id=scrape_run_id,
            job_posting_id=existing.id,
            raw_payload_ref=json.dumps({"title": job.title, "url": job.job_url})[:2000],
        )
    )
    return existing, change


def has_active_scrape_run(session: Session) -> ScrapeRun | None:
    return session.scalar(
        select(ScrapeRun).where(ScrapeRun.status == "running").limit(1)
    )


def run_scrape(
    session: Session,
    *,
    company_name: str | None = None,
    all_eligible: bool = False,
    limit: int | None = None,
    category: str | None = None,
    use_playwright: bool = False,
    settings: Settings | None = None,
    trigger: str = "manual",
    week_id: str | None = None,
    compute_job_diffs: bool = True,
    allow_overlap: bool = False,
) -> dict:
    settings = settings or get_settings()
    if not company_name and not all_eligible and not limit and not category:
        raise ValueError("Specify --company, --all-eligible, --category, or --limit")

    if not allow_overlap:
        active = has_active_scrape_run(session)
        if active is not None:
            raise RuntimeError(
                f"ScrapeRun #{active.id} is already running (week {active.week_id}). "
                "Wait for it to finish or mark it failed."
            )

    week_id = week_id or current_week_id(settings.weekly_timezone)
    companies = list(
        session.scalars(_eligible_query(session, company_name, category=category))
    )
    if company_name and not companies:
        any_row = session.scalar(select(Company).where(Company.name == company_name))
        if any_row is None:
            raise LookupError(f"Company not found: {company_name}")
        raise LookupError(
            f"Company not eligible for scrape (skip={any_row.skip}, "
            f"career_page={bool(any_row.career_page)}, status={any_row.career_page_status})"
        )
    if category and not companies and not company_name:
        raise LookupError(f"No eligible companies found for category: {category}")

    companies = [c for c in companies if c.is_eligible]
    if limit is not None:
        companies = companies[:limit]

    run = ScrapeRun(
        week_id=week_id,
        status="running",
        trigger=trigger,
        started_at=utcnow(),
        stats_json="{}",
    )
    session.add(run)
    session.flush()

    ok = 0
    failed = 0
    total_roles = 0
    total_in_scope = 0
    company_results: list[dict] = []
    marks: dict[int, str] = {}

    timeout = float(settings.scrape_timeout_seconds)

    for company in companies:
        started = utcnow()
        cr = CompanyRun(
            scrape_run_id=run.id,
            company_id=company.id,
            status="pending",
            started_at=started,
        )
        session.add(cr)
        session.flush()

        try:
            result = scrape_career_page(
                company.career_page,
                timeout,
                use_playwright=use_playwright,
                respect_robots=settings.scrape_respect_robots,
                domain_delay=settings.scrape_domain_delay_seconds,
            )
            classified = classify_jobs(result.jobs)
            in_scope_count = 0
            for job, classification in classified:
                assert isinstance(classification, Classification)
                row, change = upsert_job(
                    session, company, job, classification, week_id, run.id
                )
                marks[row.id] = change
                if classification.in_scope:
                    in_scope_count += 1

            cr.status = "success" if result.success or result.jobs else (
                "failed" if not result.success else "success"
            )
            if not result.success and not result.jobs:
                cr.status = "failed"
            cr.http_status = result.http_status
            cr.error = result.error
            cr.roles_found = len(result.jobs)
            cr.roles_in_scope = in_scope_count
            cr.parser = result.parser
            cr.finished_at = utcnow()

            if cr.status == "success":
                ok += 1
            else:
                failed += 1
            total_roles += len(result.jobs)
            total_in_scope += in_scope_count
            company_results.append(
                {
                    "company": company.name,
                    "status": cr.status,
                    "parser": result.parser,
                    "roles_found": len(result.jobs),
                    "roles_in_scope": in_scope_count,
                    "error": result.error,
                }
            )
            logger.info(
                "%s: %s roles (%s in-scope) via %s",
                company.name,
                len(result.jobs),
                in_scope_count,
                result.parser,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Scrape failed for %s", company.name)
            cr.status = "failed"
            cr.error = f"{type(e).__name__}: {e}"
            cr.finished_at = utcnow()
            failed += 1
            company_results.append(
                {
                    "company": company.name,
                    "status": "failed",
                    "parser": "",
                    "roles_found": 0,
                    "roles_in_scope": 0,
                    "error": cr.error,
                }
            )
        session.commit()

    diff_stats = {"new_roles": 0, "updated_roles": 0, "removed_roles": 0, "unchanged_roles": 0}
    if compute_job_diffs:
        ds = compute_diffs(session, run.id, marks)
        diff_stats = ds.as_dict()
        session.commit()

    if failed == 0 and ok > 0:
        status = "success"
    elif ok == 0 and len(companies) > 0:
        status = "failed"
    elif len(companies) == 0:
        status = "success"
    else:
        status = "partial"

    stats = {
        "week_id": week_id,
        "companies_targeted": len(companies),
        "companies_ok": ok,
        "companies_failed": failed,
        "roles_found": total_roles,
        "roles_in_scope": total_in_scope,
        **diff_stats,
        "companies": company_results,
    }
    run.status = status
    run.finished_at = utcnow()
    run.stats_json = json.dumps(stats)
    session.commit()

    return {
        "scrape_run_id": run.id,
        "week_id": week_id,
        "status": status,
        **stats,
    }


def export_run(
    session: Session,
    scrape_run_id: int,
    reports_dir: Path,
    *,
    in_scope_only: bool = True,
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run = session.get(ScrapeRun, scrape_run_id)
    if run is None:
        raise LookupError(f"ScrapeRun not found: {scrape_run_id}")

    # Jobs touched in this run via snapshots
    snapshot_job_ids = [
        s.job_posting_id
        for s in session.scalars(
            select(JobSnapshot).where(JobSnapshot.scrape_run_id == scrape_run_id)
        )
    ]
    jobs: list[JobPosting] = []
    if snapshot_job_ids:
        q = select(JobPosting).where(JobPosting.id.in_(snapshot_job_ids))
        if in_scope_only:
            q = q.where(JobPosting.in_scope.is_(True))
        jobs = list(session.scalars(q.order_by(JobPosting.company_id, JobPosting.title)))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = reports_dir / f"scrape_run_{scrape_run_id}_{stamp}"
    json_path = Path(str(base) + ".json")
    csv_path = Path(str(base) + ".csv")

    company_names = {
        c.id: c.name for c in session.scalars(select(Company)).all()
    }
    rows = [
        {
            "company": company_names.get(j.company_id, ""),
            "title": j.title,
            "location": j.location,
            "function": j.function,
            "seniority_band": j.seniority_band,
            "in_scope": j.in_scope,
            "job_url": j.job_url,
            "first_seen_week": j.first_seen_week,
            "last_seen_week": j.last_seen_week,
            "match_evidence": j.match_evidence,
        }
        for j in jobs
    ]

    payload = {
        "scrape_run_id": scrape_run_id,
        "week_id": run.week_id,
        "status": run.status,
        "stats": json.loads(run.stats_json or "{}"),
        "in_scope_only": in_scope_only,
        "jobs": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "company",
                "title",
                "location",
                "function",
                "seniority_band",
                "in_scope",
                "job_url",
                "first_seen_week",
                "last_seen_week",
                "match_evidence",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return json_path, csv_path
