from __future__ import annotations

from rivi.insights.schema import GroqInsightsResponse, ground_insights


def _pack():
    return {
        "summary": {"week_id": "2026-W31", "new_count": 2},
        "hottest_companies": [{"company": "Acme", "new_roles": 2}],
        "new_openings": [
            {
                "company": "Acme",
                "title": "VP Engineering",
                "job_url": "https://acme.test/1",
            },
            {
                "company": "Acme",
                "title": "Staff Data Engineer",
                "job_url": "https://acme.test/2",
            },
        ],
        "leadership_pulse": [
            {
                "company": "Acme",
                "title": "VP Engineering",
                "job_url": "https://acme.test/1",
            }
        ],
        "removals": [],
    }


def test_ground_insights_drops_invented_jobs():
    parsed = GroqInsightsResponse(
        executive_brief="Solid week.",
        priority_companies=[
            {
                "company": "Acme",
                "rationale": "Leadership hire",
                "cited_titles": ["VP Engineering", "Invented Role"],
                "cited_urls": [],
            },
            {
                "company": "FakeBank",
                "rationale": "Not in pack",
                "cited_titles": [],
                "cited_urls": [],
            },
        ],
        role_callouts=[
            {
                "company": "Acme",
                "title": "VP Engineering",
                "job_url": "https://acme.test/1",
                "why_it_matters": "Search signal",
            },
            {
                "company": "Acme",
                "title": "Made Up CTO",
                "why_it_matters": "Hallucination",
            },
        ],
        outreach_angles=[
            {"company": "Acme", "angle": "Lead with VP eng search"},
            {"company": "Ghost Co", "angle": "Should drop"},
        ],
        risk_notes=["Baseline week"],
    )
    cleaned, drops = ground_insights(parsed, _pack())
    assert any("FakeBank" in d for d in drops)
    assert any("Made Up CTO" in d for d in drops)
    assert any("Ghost Co" in d for d in drops)
    assert len(cleaned.priority_companies) == 1
    assert cleaned.priority_companies[0].company == "Acme"
    assert cleaned.priority_companies[0].cited_titles == ["VP Engineering"]
    assert len(cleaned.role_callouts) == 1
    assert cleaned.role_callouts[0].title == "VP Engineering"
    assert len(cleaned.outreach_angles) == 1


def test_schema_roundtrip_fixture_pack():
    """Smoke: fixture pack validates empty successful response shape."""
    empty = GroqInsightsResponse(
        executive_brief="Quiet week with thin signal.",
        priority_companies=[],
        role_callouts=[],
        outreach_angles=[],
        risk_notes=["Thin signal"],
    )
    cleaned, drops = ground_insights(empty, _pack())
    assert drops == []
    assert cleaned.executive_brief.startswith("Quiet")
    data = cleaned.model_dump()
    assert set(data.keys()) == {
        "executive_brief",
        "priority_companies",
        "role_callouts",
        "outreach_angles",
        "risk_notes",
    }
