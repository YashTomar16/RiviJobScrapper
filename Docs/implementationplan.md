# Implementation Plan

Plan for building Rivi from the architecture in `Docs/architecture.md`, using existing assets in `data/` and the docs in `Docs/`.

## Current baseline (done)

| Item | Status |
|------|--------|
| Problem statement, context, architecture docs | Done |
| Excel source stored (`data/Job_Scrape.xlsx`) | Done |
| Company registry (`data/companies.csv` / `.json`) | Done |
| Career-page probe (163/267 reachable) | Done |
| Role ingest, classifier | Done (Phase 2) |
| Weekly scheduler, Groq, UI | Done (Phase 3) |
| Phase 0 project bootstrap (package, CLI, config) | Done |
| Phase 1 registry hardening (DB, resolve, coverage) | Done |
| Phase 2 ingest MVP + classifier | Done |
| Phase 3 diffs, weekly, Groq, API + UI | Done |
| Phase 4 alerts, export, deep-dive, scrape polish, auth, UI | Done |

---

## Guiding principles

1. **Ship vertical slices** — each phase leaves something usable (registry health → scrape output → weekly insights).
2. **Deterministic core, LLM shell** — scrape, classify, and diff in code; Groq only for narrative/prioritization.
3. **Soft-fail per company** — one bad career page never fails the weekly run.
4. **Idempotent weeks** — re-running the same `week_id` upserts; does not duplicate jobs.
5. **No inventing jobs** — Groq must cite titles/URLs from the structured pack only.

---

## Recommended stack (v1)

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| API | FastAPI |
| DB | SQLite for local MVP → Postgres when multi-user |
| Fetch | `httpx` first; Playwright for JS-heavy boards as needed |
| Scheduler | APScheduler or cron + CLI (`python -m rivi run-weekly`) |
| LLM | Groq API |
| UI | Simple web app (FastAPI templates or lightweight React/Next) — Key Insights as home |
| Config | `.env` for `GROQ_API_KEY`, model id, schedule, concurrency |

---

## Phase 0 — Project bootstrap

**Goal:** Runnable repo skeleton and config so later phases plug in cleanly.

### Tasks

- [x] Create Python package layout (`src/rivi/` or equivalent)
- [x] Add `pyproject.toml` / `requirements.txt` (httpx, pydantic, fastapi, sqlalchemy, groq SDK, openpyxl, etc.)
- [x] Add `.env.example` (`GROQ_API_KEY`, `GROQ_MODEL`, `DATABASE_URL`, `WEEKLY_CRON`, `SCRAPE_CONCURRENCY`)
- [x] Add CLI entrypoints: `import-companies`, `resolve-careers`, `scrape`, `run-weekly`, `generate-insights`
- [x] Wire logging + structured run logs directory (`logs/` or DB)
- [x] Copy/seed `data/companies.csv` as the initial company source

### Deliverables

- Installable project; `rivi --help` works
- Env-based config documented in README

### Exit criteria

- Fresh clone → install → load companies from `data/companies.csv` without errors — **met**

---

## Phase 1 — Registry hardening

**Goal:** Maximize companies with a usable `career_page` before investing in ingest.

### Tasks

- [x] Import Excel → upsert into DB `Company` table (keep CSV export in sync)
- [x] Re-run career resolver with improved patterns (Workday, Greenhouse, Lever, Ashby, SmartRecruiters)
- [x] Support manual override of `career_page` (CLI or CSV edit + re-import)
- [x] Coverage report CLI: totals, ok / missing / failed by reason and category
- [x] Simple **Coverage health** page or markdown report under `data/reports/`

### Deliverables

- DB-backed (or improved file-backed) company registry — **SQLite `data/rivi.db`**
- Coverage report for the 104 unresolved companies — **`rivi coverage-report` → `data/reports/coverage.md`**
- Process to manually patch career URLs — **`rivi set-career-page` / `rivi skip-company`**

### Exit criteria

- Clear list of ingest-eligible companies (`career_page` present + last probe ok) — **met via coverage report**
- Documented path to fix failures (manual URL, alternate domain, mark skip) — **met in README + coverage.md**

### Depends on

- Phase 0

---

## Phase 2 — Ingest MVP + classifier

**Goal:** Manually scrape eligible career pages, classify roles, persist openings. No weekly cron yet.

### 2a. Storage schema

- [x] Implement tables from architecture: `Company`, `ScrapeRun`, `CompanyRun`, `JobPosting`, `JobSnapshot`, `JobDelta`, `WeeklyInsight`
- [x] Migrations (Alembic or equivalent) — SQLAlchemy `create_all` via `init_db`
- [x] Indexes on `company_id`, `week_id`, `job_url` / `external_id`, `in_scope`

### 2b. Ingest engine

- [x] Fetch career page HTML (httpx); detect common ATS and use listing APIs where possible
- [x] Extract: title, location, job_url, external_id (if any)
- [x] Per-company soft-fail + `CompanyRun` status
- [x] Deduplicate within a single company fetch
- [x] CLI: `rivi scrape --company "..."` and `rivi scrape --all-eligible`
- [x] Optional Playwright path behind a flag for JS-rendered boards

### 2c. Classifier

- [x] Title taxonomy rules for in-scope functions: Technology, Product, Engineering, Data, AI, ML
- [x] Seniority bands: IC, Manager, Senior Manager, Head, Director, Senior Director, VP, SVP, C-level
- [x] Out-of-scope exclusion: Sales, Marketing, Finance, HR, Legal, Operations
- [x] Output: `function`, `seniority_band`, `in_scope`, match evidence
- [x] Unit tests on a fixture title set (true positives + exclusions)

### 2d. Manual run output

- [x] Persist all postings; filter views to `in_scope = true`
- [x] Export snapshot JSON/CSV for a run (debug + stakeholder share)

### Deliverables

- Working scrape for pilot ATS boards (Workday + Greenhouse verified)
- Classified in-scope job store (`job_postings`)
- Classifier test suite (`tests/test_classifier.py` — 14 passed)

### Exit criteria

- Pilot companies produce stable job lists on repeat scrape (idempotent upserts) — **met**
- Classifier precision acceptable on sampled titles — **unit tests + live samples**
- Failures isolated per company with visible errors — **met**

### Depends on

- Phase 1 (enough eligible career pages)

---

## Phase 3 — Diffs, weekly scheduler, Groq Key Insights, UI

**Goal:** Full weekly loop ending in Key Insights (structured + Groq) in the UI.

### 3a. Change detection

- [x] Role identity: prefer `external_id` / stable `job_url`; fallback normalized title + company + location
- [x] Compute `new` / `updated` / `removed` / `unchanged` vs prior week
- [x] Write `JobDelta` rows; update `first_seen_week` / `last_seen_week` / `status`

### 3b. Weekly scheduler

- [x] `week_id` = ISO week (config timezone)
- [x] Orchestrator implementing architecture sequence:
  1. Load eligible companies  
  2. Ingest + classify  
  3. Diff  
  4. Aggregate structured insights  
  5. Call Groq  
  6. Persist `WeeklyInsight`  
  7. Mark `ScrapeRun` complete  
- [x] Cron / APScheduler weekly trigger + `rivi run-weekly` manual
- [x] Idempotent re-run for same `week_id`
- [x] Run stats: companies_ok, companies_failed, new_roles, removed_roles

### 3c. Structured aggregates

- [x] Week summary counts
- [x] New openings list
- [x] Leadership / executive pulse (Head+)
- [x] Hottest companies
- [x] Function + seniority mix
- [x] Removals
- [x] Coverage gaps

### 3d. Groq insights layer

- [x] Define JSON response schema: `executive_brief`, `priority_companies[]`, `role_callouts[]`, `outreach_angles[]`, `risk_notes[]`
- [x] System prompt: Riviera search enablement; cite only provided companies/titles/URLs
- [x] Build compact context pack from aggregates (token-budget aware)
- [x] Groq client wrapper (model, temperature, max tokens from env)
- [x] Persist `groq_model`, `groq_prompt_version`, `llm_status`, brief, priorities, raw ref
- [x] Fallback: publish structured insights if Groq fails; `llm_status = failed`
- [x] CLI: `rivi generate-insights --week YYYY-Www` (retry without re-scrape)
- [x] Smoke test with fixture weekly pack (no live scrape)

### 3e. API

- [x] `GET /insights/latest` and `GET /insights/{week_id}`
- [x] `GET /jobs?week=&in_scope=&seniority=`
- [x] `GET /companies` + coverage fields
- [x] `GET /runs/{id}` status
- [x] `POST /insights/{week_id}/regenerate` (Groq only)

### 3f. Key Insights UI

- [x] Home = latest week Key Insights
- [x] Top: Groq executive brief + priority companies + outreach angles
- [x] Evidence tables: new jobs, leadership pulse, hottest companies, mixes
- [x] Coverage gaps section
- [x] Week switcher (prior weeks)
- [x] Secondary views: All openings, Company detail, Coverage health
- [x] Job rows link to source URL; show first-seen

### Deliverables

- End-to-end weekly pipeline — **`rivi run-weekly`**
- Groq-enriched Key Insights page — **`rivi serve` → `/`**
- Manual + scheduled run paths — **CLI + `rivi serve --scheduler`**

### Exit criteria

- One successful full weekly run on eligible companies
- Key Insights shows structured lists + Groq brief grounded in real postings
- Groq outage still shows structured insights; regenerate works
- Re-running the same week does not duplicate jobs

### Depends on

- Phase 2

---

## Phase 4 — Enablement polish

**Goal:** Make the weekly signal actionable for researchers day-to-day.

### Tasks

- [x] Alerts for new Head+ / VP+ / C-level roles (Slack or email)
- [x] Historical week browser UX polish
- [x] Export week pack (CSV / JSON) for CRM / BD
- [x] Optional on-demand Groq company deep-dive
- [x] Improve ATS adapters based on failure logs
- [x] Rate-limit tuning per domain; robots/ToS-aware delays
- [x] Basic auth for UI if exposed beyond localhost

### Deliverables

- Notification path for high-seniority signal — **`rivi send-alerts` + weekly hook**
- Export + optional deep-dive — **`rivi export-week` / `rivi deep-dive`**
- Hardened scrape coverage — **domain pacer, robots, 429 retries, GH embed discovery**

### Exit criteria

- Stakeholders receive/use weekly Key Insights without engineering help
- High-seniority alerts validated on a real week

### Depends on

- Phase 3

---

## Workstream map (parallelism)

```
Phase 0 ──▶ Phase 1 ──▶ Phase 2a schema
                │              │
                │              ├──▶ Phase 2b ingest ──┐
                │              └──▶ Phase 2c classify ─┼──▶ Phase 3a–3d pipeline
                │                                     │
                └──── coverage UI (light) ────────────┴──▶ Phase 3e–3f API + UI
                                                              │
                                                              ▼
                                                         Phase 4 polish
```

Classifier (2c) can proceed in parallel with ingest (2b) using fixture titles.

---

## Milestone checklist

| Milestone | Outcome |
|-----------|---------|
| **M0** | Repo + CLI + config |
| **M1** | Eligible company list trusted for scrape |
| **M2** | Manual scrape + classified jobs for eligible set |
| **M3** | Weekly run → Key Insights UI (structured + Groq) |
| **M4** | Alerts, export, deeper enablement |

---

## Testing plan (by phase)

| Phase | Focus |
|-------|--------|
| 1 | Import idempotency; resolver status codes |
| 2 | Parser fixtures per ATS type; classifier unit tests; scrape upsert idempotency |
| 3 | Diff correctness (new/removed); Groq schema validation; grounded-citation checks; scheduler dry-run |
| 4 | Alert filters; export integrity |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Many career pages JS-only / blocked | ATS adapters + Playwright selectively; track coverage gaps |
| Unresolved career URLs (~104) | Manual override workflow before expanding scrape |
| Classifier false positives (Finance “quant”, etc.) | Tight exclusion rules + sampled human review each phase |
| Groq hallucination | Strict prompt + JSON schema; UI always shows source job links |
| Site rate limits / ToS | Low concurrency, domain pacing, cache weekly snapshots |
| Brittle HTML parsers | Prefer ATS APIs; version parsers; soft-fail |

---

## Open decisions to lock before / during build

Resolve these early so Phase 3 does not stall:

1. Weekly run day/time + timezone  
2. Scrape concurrency and per-domain rate limits  
3. Playwright vs HTTP-only for v1  
4. Slack push vs UI-only for v1 alerts  
5. SQLite vs Postgres for MVP  
6. Groq model id, temperature, max tokens  
7. Exact Groq response JSON schema  

---

## Suggested first sprint (concrete)

1. Phase 0 bootstrap  
2. Load `data/companies.csv` into DB  
3. Coverage report for missing career pages  
4. Scrape + classify **5 pilot companies** with known-good career URLs  
5. Sketch Key Insights page with fixture data (no Groq yet)  
6. Wire Groq on fixture weekly pack → validate schema + grounding  

Then expand scrape to all eligible companies and add scheduler.

---

## Out of scope (do not build)

- Candidate sourcing / resume search  
- Apply-to-job / ATS write-back  
- CRM replacement  
- Companies outside the provided registry  
- Ingesting Sales, Marketing, Finance, HR, Legal, Operations roles as primary signal  
