# Streamlit Hosting Plan

Plan to expose Rivi’s Key Insights and job browse experience as a **Streamlit** app, while keeping scrape / classify / Groq / CLI as the existing Python package.

## Why Streamlit

- Faster iteration for recruiter-facing dashboards (filters, tables, downloads)
- Easy local demos and lightweight cloud hosts (Streamlit Community Cloud, Hugging Face Spaces, internal VM)
- Same SQLAlchemy models / aggregates / export helpers — no second data pipeline

## What stays vs what moves

| Layer | Keep as-is | Streamlit role |
|-------|------------|----------------|
| Company registry, scrape, classifier, diffs | `rivi` package + CLI | Call via shared libs only (no scrape-from-UI in v1) |
| Groq weekly insights | `rivi.insights` | Display + “Regenerate” button (optional) |
| FastAPI + Jinja UI | Keep until Streamlit parity | Parallel UI; retire later if Streamlit wins |
| SQLite / `DATABASE_URL` | Same DB | Streamlit reads (and limited writes) via `session_scope` |

**Principle:** Streamlit is a **presentation + light action** shell over existing services. Do not reimplement scraping or classification inside Streamlit pages.

## Target pages (parity with current UI)

Map today’s FastAPI routes to Streamlit multipage app:

| Streamlit page | Current UI | Primary data |
|----------------|------------|--------------|
| `Home` / Key Insights | `/` | `get_insight_payload`, aggregates, Groq brief |
| `Jobs` | `/jobs` | `JobPosting` in-scope filters (company, function, seniority, week) |
| `Companies` | `/companies` | Registry + eligibility + career page |
| `Company detail` | company page | Open roles + optional deep-dive |
| `Weeks` | `/weeks` | Historical `WeeklyInsight` list |
| `Coverage` | `/coverage` | `build_coverage_report` |
| `Export` | export API | `export_week_pack` → download CSV/JSON |

Nice-to-haves after parity:

- Wells Fargo–style multi-URL career boards called out on company detail
- Leadership-only toggle (Head+ / Director+ / VP+ / C-level)
- Thin-week / baseline-week banners from aggregates

## Proposed layout

```
src/rivi/streamlit_app/
  __init__.py
  app.py                 # streamlit entry (or root streamlit_app.py)
  pages/
    1_Key_Insights.py
    2_Jobs.py
    3_Companies.py
    4_Coverage.py
    5_Weeks.py
  components/
    filters.py
    job_table.py
    insight_cards.py
  data_access.py         # thin wrappers around aggregates / models / export
```

Entry command:

```bash
streamlit run src/rivi/streamlit_app/app.py
# or
rivi serve-streamlit   # thin CLI wrapper (phase 2)
```

## Data access rules

1. Reuse `get_settings()`, `session_scope()`, `build_aggregates`, `get_insight_payload`, `build_coverage_report`, `export_week_pack`.
2. Cache read-heavy queries with `@st.cache_data(ttl=60)` keyed by `week_id` / filters — invalidate after regenerate.
3. Writes allowed in v1 only for:
   - `generate_insights` / `regenerate_llm_only` (explicit button)
   - optional company deep-dive
4. Do **not** trigger `--all-eligible` scrapes from Streamlit in v1 (long-running, locks SQLite). Keep scrapes on CLI / scheduler.

## Auth & secrets

| Concern | Approach |
|---------|----------|
| App gate | Streamlit secrets or env: `STREAMLIT_AUTH_USER` / `STREAMLIT_AUTH_PASSWORD` (or reuse `BASIC_AUTH_*`) |
| Groq | `GROQ_API_KEY` in `.streamlit/secrets.toml` or env (never commit) |
| DB | `DATABASE_URL` pointing at shared `data/rivi.db` or hosted Postgres later |
| Network | Bind `localhost` for demos; reverse proxy + HTTPS for shared host |

## Hosting options

### A. Local / internal demo (first)

```bash
pip install -e ".[streamlit]"   # add optional dep
streamlit run src/rivi/streamlit_app/app.py --server.port 8501
```

URL: `http://127.0.0.1:8501`

### B. Streamlit Community Cloud

- Push repo (or private GitHub)
- Set secrets: `GROQ_API_KEY`, `DATABASE_URL` (or ship a read-only snapshot DB)
- **Caveat:** SQLite on ephemeral disk is fragile; prefer read-only demo DB or remote Postgres
- Scraping/Playwright generally **not** suitable on Community Cloud

### C. VM / Docker (recommended for Riviera internal)

- Image runs: weekly scheduler (or cron) + Streamlit UI
- Persist `data/` volume for SQLite (or migrate to Postgres)
- Playwright + Chromium as optional sidecar / same image profile
- Basic auth or SSO in front (nginx / Cloudflare Access)

### D. Keep FastAPI API + Streamlit front

Longer-term option: Streamlit calls FastAPI JSON endpoints instead of DB directly. Better if multiple UIs or mobile clients appear. Not required for v1.

## Implementation phases

### Phase 0 — Plan & deps (this doc)

- [x] Write Streamlit plan
- [ ] Add optional `[project.optional-dependencies] streamlit = ["streamlit>=1.32"]`
- [ ] Decide: replace FastAPI UI vs run both

### Phase 1 — Read-only MVP

- [ ] Scaffold `streamlit_app` + Home (Key Insights for latest week)
- [ ] Jobs page with filters + link-out to `job_url`
- [ ] Companies + Coverage pages
- [ ] Week selector shared in sidebar
- [ ] Export download button for current week

**Exit criteria:** Researcher can browse 2026-W31 in-scope roles (incl. Wells Fargo Technology Directors) without CLI.

### Phase 2 — Actions

- [ ] “Regenerate Groq insights” with clear failure UI (token budget / TPM)
- [ ] Company deep-dive button
- [ ] Show `llm_status`, truncation notes, coverage gaps prominently
- [ ] `rivi serve-streamlit` CLI

### Phase 3 — Host

- [ ] Dockerfile + compose (`ui` + optional `scheduler`)
- [ ] Secrets / auth checklist
- [ ] Postgres path if multi-writer (scrape + UI) becomes painful on SQLite
- [ ] Smoke test: import companies → scrape sample → open Streamlit → export

### Phase 4 — Cleanup (optional)

- [ ] Feature-flag or deprecate Jinja FastAPI pages
- [ ] Update README + architecture.md “UI” section
- [ ] Align branding (Riviera Flamingo) in Streamlit theme (`config.toml`)

## Design notes (Streamlit-specific)

- Prefer **one job per section**: Insights first; jobs/coverage as separate pages (avoid dashboard clutter on Home).
- Home should lead with week brief + priority companies; raw tables live on Jobs.
- Use Streamlit theme tokens (`[theme]` in `.streamlit/config.toml`) for Riviera accent `#F26622` — avoid generic purple defaults.
- Large job lists: `st.dataframe` with column config (link columns), not hundreds of expanders.
- Groq pack size: Streamlit regenerate must use the same (or tighter) `compact_context_pack` caps so TPM 12k failures are handled with a visible message.

## Risks

| Risk | Mitigation |
|------|------------|
| SQLite lock (scrape + UI write) | UI read-mostly; regenerate only when scrape idle; later Postgres |
| Community Cloud ephemeral storage | Demo snapshot DB or external DB |
| Playwright / scrape on Streamlit host | Out of scope for UI host; run scrape elsewhere |
| Dual UI drift (FastAPI vs Streamlit) | Shared `data_access.py`; one source of query logic |
| Groq 413 token limit | Already observed at ~200 in-scope roles; shrink pack before host launch |

## Open decisions

1. **Replace or parallel?** Recommend parallel until Phase 1 parity signed off.
2. **Who can regenerate Groq?** All authenticated users vs admin-only.
3. **Live scrape buttons?** Default no for v1.
4. **Postgres timeline?** Only when concurrent scrape + UI writers conflict.

## Success metrics

- Time-to-first-insight for a researcher &lt; 30s after opening the app
- All in-scope Wells Fargo Technology Director roles visible on Jobs with working links
- Export CSV matches CLI `rivi export-week` for the same `week_id`
- Groq failure shows structured insights still available (same behavior as FastAPI)

## Suggested first PR

1. Add `Docs/streamlit-plan.md` (this file)
2. Optional dep + empty `streamlit_app/app.py` hello page reading `current_week_id` + in-scope job count
3. Stop — review with stakeholders before building full multipage UI
