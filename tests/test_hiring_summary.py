from rivi.hiring_summary import company_hiring_summaries, format_hiring_summary


def test_format_both_bands():
    assert (
        format_hiring_summary(
            ic_count=30,
            non_ic_count=5,
            functions=["Engineering", "AI", "Product"],
        )
        == "Hiring for 5 non-IC and 30 IC roles across Engineering, AI, Product"
    )


def test_format_ic_only():
    assert (
        format_hiring_summary(ic_count=12, non_ic_count=0, functions=["Engineering"])
        == "Hiring for 12 IC roles across Engineering"
    )


def test_format_non_ic_only():
    assert (
        format_hiring_summary(ic_count=0, non_ic_count=3, functions=["Product", "Data"])
        == "Hiring for 3 non-IC roles across Product, Data"
    )


def test_company_hiring_summaries_aggregates():
    jobs = [
        {"company": "xAI", "seniority": "IC", "function": "Engineering", "category": "Startups"},
        {"company": "xAI", "seniority": "IC", "function": "AI", "category": "Startups"},
        {"company": "xAI", "seniority_band": "Director", "function": "Engineering", "category": "Startups"},
        {"company": "Acme", "seniority": "Manager", "function": "Product", "category": "Startups"},
    ]
    rows = company_hiring_summaries(jobs)
    assert len(rows) == 2
    xai = next(r for r in rows if r["company"] == "xAI")
    assert xai["total"] == 3
    assert xai["ic_count"] == 2
    assert xai["non_ic_count"] == 1
    assert xai["functions"][0] == "Engineering"  # highest volume first
    assert "2 IC" in xai["hiring_summary"]
    assert "1 non-IC" in xai["hiring_summary"]
    # Sorted by total desc — xAI (3) before Acme (1)
    assert rows[0]["company"] == "xAI"
