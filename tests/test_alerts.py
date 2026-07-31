from __future__ import annotations

from rivi.alerts import ALERT_SENIORITY, format_alert_text


def test_alert_seniority_includes_head_and_vp():
    assert "Head" in ALERT_SENIORITY
    assert "VP" in ALERT_SENIORITY
    assert "C-level" in ALERT_SENIORITY
    assert "IC" not in ALERT_SENIORITY
    assert "Manager" not in ALERT_SENIORITY


def test_format_alert_text_includes_roles():
    roles = [
        {
            "company": "Acme",
            "title": "VP Engineering",
            "seniority_band": "VP",
            "job_url": "https://acme.test/1",
        }
    ]
    text = format_alert_text("2026-W31", roles)
    assert "2026-W31" in text
    assert "Acme" in text
    assert "VP Engineering" in text
    assert "https://acme.test/1" in text
