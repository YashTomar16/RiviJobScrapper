from __future__ import annotations

import json

from rivi.export import build_week_pack, export_week_pack
from rivi.models import (
    Base,
    Company,
    CompanyRun,
    JobDelta,
    JobPosting,
    JobSnapshot,
    ScrapeRun,
    WeeklyInsight,
    make_session_factory,
)


def _seed(tmp_path):
    url = f"sqlite:///{tmp_path / 'export.db'}"
    factory, engine = make_session_factory(url)
    Base.metadata.create_all(engine)
    session = factory()

    company = Company(
        name="Acme",
        category="Banks",
        career_page="https://acme.test/jobs",
        career_page_status="ok:200",
    )
    session.add(company)
    session.flush()

    run = ScrapeRun(week_id="2026-W31", status="success", stats_json='{"companies_ok":1}')
    session.add(run)
    session.flush()
    session.add(
        CompanyRun(
            scrape_run_id=run.id,
            company_id=company.id,
            status="success",
            roles_found=1,
            roles_in_scope=1,
        )
    )
    job = JobPosting(
        company_id=company.id,
        identity_key="ext:1",
        title="VP Engineering",
        function="Engineering",
        seniority_band="VP",
        in_scope=True,
        job_url="https://acme.test/1",
        first_seen_week="2026-W31",
        last_seen_week="2026-W31",
        status="open",
    )
    session.add(job)
    session.flush()
    session.add(JobSnapshot(scrape_run_id=run.id, job_posting_id=job.id))
    session.add(
        JobDelta(scrape_run_id=run.id, job_posting_id=job.id, change_type="new")
    )
    session.add(
        WeeklyInsight(
            week_id="2026-W31",
            scrape_run_id=run.id,
            summary_json="{}",
            llm_status="skipped",
            llm_brief="",
            llm_priorities_json="{}",
        )
    )
    session.commit()
    return session


def test_export_week_pack_json_csv(tmp_path):
    session = _seed(tmp_path)
    pack = build_week_pack(session, "2026-W31")
    assert pack["week_id"] == "2026-W31"
    assert pack["summary"]["new_count"] == 1
    assert pack["new_openings"][0]["title"] == "VP Engineering"

    out = tmp_path / "out"
    json_path, csv_path = export_week_pack(session, "2026-W31", out_dir=out)
    assert json_path.exists()
    assert csv_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["week_id"] == "2026-W31"
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "VP Engineering" in csv_text
    assert "new_openings" in csv_text
