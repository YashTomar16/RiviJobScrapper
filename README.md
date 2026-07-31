# Rivi

Career-page monitoring and weekly hiring **Key Insights** for Riviera Partners.

See `Docs/` for problem statement, architecture, implementation plan, and edge cases.

## Status

Phases **0–4** are implemented: registry, scrape + classifier, weekly diffs, Groq insights, alerts, export, deep-dive, and Key Insights UI (Atlassian Design System patterns + Riviera Flamingo branding).

## Setup

```bash
cd /path/to/Rivi
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # set GROQ_API_KEY; optional Slack/SMTP/basic auth
```

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `GROQ_API_KEY` | Groq API key for Key Insights | _(empty)_ |
| `GROQ_MODEL` | Groq model id | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | SQLAlchemy DB URL | `sqlite:///./data/rivi.db` |
| `WEEKLY_CRON` | Weekly schedule (cron) | `0 6 * * 1` |
| `WEEKLY_TIMEZONE` | Scheduler timezone | `UTC` |
| `SCRAPE_DOMAIN_DELAY_SECONDS` | Per-domain pacing | `0.5` |
| `SCRAPE_RESPECT_ROBOTS` | Honor robots.txt | `true` |
| `SLACK_WEBHOOK_URL` | High-seniority Slack alerts | _(empty)_ |
| `ALERT_EMAIL_TO` / `SMTP_*` | Email alerts | _(empty)_ |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD` | UI basic auth | _(empty = off)_ |
| `LOG_LEVEL` | Logging level | `INFO` |

## CLI

```bash
rivi --help

# Registry + scrape
rivi import-companies
rivi resolve-careers --missing-only
rivi coverage-report
rivi scrape --limit 10
rivi scrape --all-eligible

# Weekly pipeline
rivi run-weekly
rivi run-weekly --limit 5 --skip-groq --skip-alerts
rivi generate-insights --week 2026-W31 --regenerate

# Phase 4 enablement
rivi export-week --week 2026-W31
rivi send-alerts --week 2026-W31
rivi deep-dive --company "Northern Trust"

# UI + API
rivi serve
rivi serve --scheduler
```

### UI

```bash
rivi serve   # http://127.0.0.1:8000/
```

- `/` — Key Insights (week switcher + export)
- `/weeks` — historical week browser
- `/jobs`, `/companies`, `/coverage`
- Company detail → **Groq deep-dive** button
- Set `BASIC_AUTH_USER` + `BASIC_AUTH_PASSWORD` before exposing beyond localhost

UI follows **Atlassian Design System** layout/tokens with **Riviera Flamingo** (`#F26622`) as the brand accent.

### Alerts

After each weekly run (unless `--skip-alerts`), Rivi notifies on **new Head+ / VP+ / C-level** in-scope roles via Slack webhook and/or SMTP. Baseline first weeks are suppressed. Deduped per `week_id`.

### Export

```bash
rivi export-week --week 2026-W31
# → data/reports/week_pack_2026_W31_*.{json,csv}
```

Also available at `/api/export/{week_id}` and `/api/export/{week_id}?format=csv`.

## Layout

```
Docs/           # product & technical docs
data/           # companies seed, rivi.db, reports/
logs/           # rivi.log + runs/ + alerts/
src/rivi/       # package (ingest, insights, alerts, export, web)
tests/
```
