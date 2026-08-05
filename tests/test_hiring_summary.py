from rivi.hiring_summary import (
    company_hiring_summaries,
    format_hiring_summary,
    top_senior_titles,
)


def test_format_with_top_titles():
    assert (
        format_hiring_summary(
            ic_count=30,
            non_ic_count=5,
            functions=["Engineering", "AI", "Product"],
            top_titles=["Director of Product", "VP Engineering"],
        )
        == (
            "Hiring for Director of Product + VP Engineering + 5 non-IC and 30 IC roles "
            "across Engineering, AI, Product"
        )
    )


def test_format_ic_only_with_title():
    assert (
        format_hiring_summary(
            ic_count=12,
            non_ic_count=0,
            functions=["Engineering"],
            top_titles=["Staff Software Engineer"],
        )
        == "Hiring for Staff Software Engineer + 12 IC roles across Engineering"
    )


def test_format_non_ic_only():
    assert (
        format_hiring_summary(
            ic_count=0,
            non_ic_count=3,
            functions=["Product", "Data"],
            top_titles=["Director of Product"],
        )
        == "Hiring for Director of Product + 3 non-IC roles across Product, Data"
    )


def test_top_senior_titles_prefers_non_ic_by_band():
    jobs = [
        {"title": "Software Engineer", "seniority": "IC"},
        {"title": "Director of Product", "seniority": "Director"},
        {"title": "VP Engineering", "seniority": "VP"},
        {"title": "Engineering Manager", "seniority": "Manager"},
    ]
    assert top_senior_titles(jobs, limit=2) == ["VP Engineering", "Director of Product"]


def test_company_hiring_summaries_includes_top_roles():
    jobs = [
        {
            "company": "xAI",
            "title": "ML Engineer",
            "seniority": "IC",
            "function": "AI",
            "category": "Startups",
        },
        {
            "company": "xAI",
            "title": "Backend Engineer",
            "seniority": "IC",
            "function": "Engineering",
            "category": "Startups",
        },
        {
            "company": "xAI",
            "title": "Director of Product",
            "seniority_band": "Director",
            "function": "Product",
            "category": "Startups",
        },
        {
            "company": "xAI",
            "title": "Head of Engineering",
            "seniority": "Head",
            "function": "Engineering",
            "category": "Startups",
        },
    ]
    rows = company_hiring_summaries(jobs)
    xai = rows[0]
    assert xai["company"] == "xAI"
    assert xai["top_titles"] == ["Director of Product", "Head of Engineering"]
    assert xai["hiring_summary"].startswith(
        "Hiring for Director of Product + Head of Engineering +"
    )
    assert "2 non-IC and 2 IC roles" in xai["hiring_summary"]
