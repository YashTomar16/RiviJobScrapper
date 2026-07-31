from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from rivi.aggregates import build_aggregates
from rivi.config import Settings, get_settings

logger = logging.getLogger("rivi.alerts")

# Head+ / VP+ / C-level for Phase 4 alerts
ALERT_SENIORITY = frozenset(
    {"Head", "Director", "Senior Director", "VP", "SVP", "C-level"}
)


def high_seniority_new_roles(
    session: Session,
    *,
    scrape_run_id: int | None = None,
    week_id: str | None = None,
) -> list[dict[str, Any]]:
    """New in-scope roles at Head+ from a scrape run / week."""
    aggregates = build_aggregates(
        session, scrape_run_id=scrape_run_id, week_id=week_id
    )
    summary = aggregates["summary"]
    # N1: suppress baseline first week (everything "new")
    if summary.get("baseline_week"):
        logger.info("Skipping high-seniority alerts — baseline week %s", summary["week_id"])
        return []

    roles = [
        r
        for r in aggregates.get("leadership_pulse", [])
        if r.get("change_type") == "new" and r.get("seniority_band") in ALERT_SENIORITY
    ]
    return roles


def format_alert_text(week_id: str, roles: list[dict[str, Any]]) -> str:
    lines = [
        f"*Rivi high-seniority alert — {week_id}*",
        f"{len(roles)} new Head+ / VP+ / C-level in-scope role(s):",
        "",
    ]
    for r in roles[:40]:
        title = r.get("title") or ""
        company = r.get("company") or ""
        band = r.get("seniority_band") or ""
        url = r.get("job_url") or ""
        line = f"• *{company}* — {title} ({band})"
        if url:
            line += f"\n  {url}"
        lines.append(line)
    if len(roles) > 40:
        lines.append(f"…and {len(roles) - 40} more")
    return "\n".join(lines)


def _alert_sent_marker(settings: Settings, week_id: str) -> Path:
    path = settings.logs_dir / "alerts"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"seniority_{week_id}.sent"


def already_sent(settings: Settings, week_id: str) -> bool:
    return _alert_sent_marker(settings, week_id).exists()


def mark_sent(settings: Settings, week_id: str, payload: dict) -> None:
    path = _alert_sent_marker(settings, week_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def send_slack(webhook_url: str, text: str) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(webhook_url, json={"text": text})
        if resp.status_code >= 400:
            raise RuntimeError(f"Slack webhook HTTP {resp.status_code}: {resp.text[:200]}")


def send_email(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    mail_from: str,
    mail_to: str,
    subject: str,
    body: str,
    use_tls: bool = True,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)


def dispatch_seniority_alerts(
    session: Session,
    *,
    week_id: str,
    scrape_run_id: int | None = None,
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Send Slack/email for new high-seniority roles. Deduped per week_id (N2)."""
    settings = settings or get_settings()
    result: dict[str, Any] = {
        "week_id": week_id,
        "roles": 0,
        "skipped": False,
        "slack": "skipped",
        "email": "skipped",
    }

    if not force and already_sent(settings, week_id):
        result["skipped"] = True
        result["reason"] = "already_sent"
        logger.info("Alerts already sent for %s — skip (use force to override)", week_id)
        return result

    try:
        roles = high_seniority_new_roles(
            session, scrape_run_id=scrape_run_id, week_id=week_id
        )
    except LookupError as e:
        result["skipped"] = True
        result["reason"] = str(e)
        return result

    result["roles"] = len(roles)
    if not roles:
        result["skipped"] = True
        result["reason"] = "no_high_seniority_roles"
        # Still mark so quiet weeks don't re-fire endlessly on re-run
        if not force:
            mark_sent(settings, week_id, {"roles": 0, "reason": "empty"})
        return result

    text = format_alert_text(week_id, roles)
    plain = text.replace("*", "")

    if settings.slack_webhook_url:
        try:
            send_slack(settings.slack_webhook_url, text)
            result["slack"] = "sent"
        except Exception as e:  # noqa: BLE001
            logger.exception("Slack alert failed")
            result["slack"] = f"failed:{e}"

    if settings.alert_email_to and settings.smtp_host:
        try:
            send_email(
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                mail_from=settings.alert_email_from or settings.smtp_username,
                mail_to=settings.alert_email_to,
                subject=f"Rivi: {len(roles)} high-seniority roles — {week_id}",
                body=plain,
                use_tls=settings.smtp_tls,
            )
            result["email"] = "sent"
        except Exception as e:  # noqa: BLE001
            logger.exception("Email alert failed")
            result["email"] = f"failed:{e}"

    if not settings.slack_webhook_url and not (
        settings.alert_email_to and settings.smtp_host
    ):
        result["reason"] = "no_channel_configured"
        # Write draft for operators
        draft = settings.reports_dir / f"alert_draft_{week_id}.txt"
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        draft.write_text(plain, encoding="utf-8")
        result["draft"] = str(draft)

    mark_sent(settings, week_id, result)
    return result
