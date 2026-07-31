from __future__ import annotations

from sqlalchemy import select

from rivi.diff import DiffStats, compute_diffs, metadata_changed
from rivi.models import (
    Base,
    Company,
    CompanyRun,
    JobDelta,
    JobPosting,
    JobSnapshot,
    ScrapeRun,
    make_session_factory,
)


def _session(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    factory, engine = make_session_factory(url)
    Base.metadata.create_all(engine)
    return factory()


def test_metadata_changed_detects_title_and_location():
    job = JobPosting(
        company_id=1,
        identity_key="url:https://x/1",
        title="Engineer",
        location="NY",
        job_url="https://x/1",
    )
    assert metadata_changed(job, "Senior Engineer", "NY", "https://x/1")
    assert metadata_changed(job, "Engineer", "SF", "https://x/1")
    assert not metadata_changed(job, "Engineer", "NY", "https://x/1?utm_source=a")


def test_diff_new_updated_removed(tmp_path):
    session = _session(tmp_path)
    company = Company(
        name="Acme",
        category="Banks",
        website="https://acme.test",
        career_page="https://acme.test/careers",
        career_page_status="ok:200",
    )
    session.add(company)
    session.flush()

    run = ScrapeRun(week_id="2026-W31", status="success", trigger="test")
    session.add(run)
    session.flush()

    cr = CompanyRun(
        scrape_run_id=run.id,
        company_id=company.id,
        status="success",
        roles_found=2,
        roles_in_scope=2,
    )
    session.add(cr)

    new_job = JobPosting(
        company_id=company.id,
        identity_key="ext:1",
        title="Software Engineer",
        location="NY",
        job_url="https://acme.test/jobs/1",
        function="Engineering",
        seniority_band="IC",
        in_scope=True,
        first_seen_week="2026-W31",
        last_seen_week="2026-W31",
        status="open",
    )
    updated_job = JobPosting(
        company_id=company.id,
        identity_key="ext:2",
        title="VP Engineering",
        location="SF",
        job_url="https://acme.test/jobs/2",
        function="Engineering",
        seniority_band="VP",
        in_scope=True,
        first_seen_week="2026-W30",
        last_seen_week="2026-W31",
        status="open",
    )
    removed_job = JobPosting(
        company_id=company.id,
        identity_key="ext:3",
        title="Data Engineer",
        location="NY",
        job_url="https://acme.test/jobs/3",
        function="Data",
        seniority_band="IC",
        in_scope=True,
        first_seen_week="2026-W29",
        last_seen_week="2026-W30",
        status="open",
    )
    session.add_all([new_job, updated_job, removed_job])
    session.flush()

    session.add_all(
        [
            JobSnapshot(scrape_run_id=run.id, job_posting_id=new_job.id),
            JobSnapshot(scrape_run_id=run.id, job_posting_id=updated_job.id),
        ]
    )
    session.commit()

    marks = {new_job.id: "new", updated_job.id: "updated"}
    stats = compute_diffs(session, run.id, marks)
    session.commit()

    assert isinstance(stats, DiffStats)
    assert stats.new == 1
    assert stats.updated == 1
    assert stats.removed == 1

    deltas = {d.change_type for d in session.scalars(select(JobDelta)).all()}
    assert deltas == {"new", "updated", "removed"}

    session.refresh(removed_job)
    assert removed_job.status == "removed"


def test_no_removal_on_failed_company(tmp_path):
    session = _session(tmp_path)
    company = Company(
        name="FailCo",
        career_page="https://fail.test/jobs",
        career_page_status="ok:200",
    )
    session.add(company)
    session.flush()
    run = ScrapeRun(week_id="2026-W31", status="partial")
    session.add(run)
    session.flush()
    session.add(
        CompanyRun(
            scrape_run_id=run.id,
            company_id=company.id,
            status="failed",
            error="timeout",
        )
    )
    job = JobPosting(
        company_id=company.id,
        identity_key="ext:9",
        title="Engineer",
        in_scope=True,
        status="open",
        first_seen_week="2026-W30",
        last_seen_week="2026-W30",
    )
    session.add(job)
    session.commit()

    stats = compute_diffs(session, run.id, marks={})
    session.commit()
    assert stats.removed == 0
    session.refresh(job)
    assert job.status == "open"
