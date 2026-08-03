from rivi.ingest.rate_limit import _longest_match_allows, _parse_robots_rules


EIGHTFOLD_ROBOTS = """
User-agent: *
Disallow: /
Allow: /$
Allow: /careers
Allow: /api/apply
Allow: /api/pcsx
"""


def test_eightfold_style_allow_overrides_disallow_root():
    rules = _parse_robots_rules(EIGHTFOLD_ROBOTS)
    assert _longest_match_allows("/careers", rules) is True
    assert _longest_match_allows("/api/apply/v2/jobs", rules) is True
    assert _longest_match_allows("/api/pcsx/search", rules) is True
    assert _longest_match_allows("/secret", rules) is False
    assert _longest_match_allows("/", rules) is False
