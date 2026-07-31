# Architecture

## Overview

Rivi is a career-page monitoring platform for Riviera Partners. It tracks hiring across a curated list of ~200–300 companies (asset managers and banks today), ingests open roles from their career pages on a weekly schedule, filters to technology-relevant functions, and surfaces the weekly haul as **Key Insights** for research and sales enablement teams. Structured weekly deltas are passed to **Groq** (LLM) to generate recruiter-facing narratives, prioritization, and outreach angles.

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌────────────┐     ┌──────────────────┐
│ Company      │────▶│ Career Page      │────▶│ Role Ingest &   │────▶│ Groq LLM   │────▶│ Key Insights UI  │
│ Registry     │     │ Resolver         │     │ Classifier      │     │ Insights   │     │                  │
│ (Excel/CSV)  │     │                  │     │ + weekly deltas │     │            │     │                  │
└─────────────┘     └──────────────────┘     └────────┬────────┘     └────────────┘     └──────────────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │ Weekly         │
                                              │ Scheduler      │
                                              └────────────────┘
```

## Goals

| Goal | How architecture supports it |
|------|------------------------------|
| Reduce manual career-page checking | Automated weekly scrape of known career URLs |
| Catch new / updated / removed roles | Diff against prior week’s snapshot |
| Focus on relevant openings only | Function + seniority classifier |
| Act on weekly signal quickly | Key Insights view of each week’s sourced jobs |
| Turn raw deltas into actionable intel | Groq LLM summarizes, ranks, and explains weekly signals |
| Scale to 200–300 companies | Batch ingest + durable company registry |

## Current data assets

Located under `data/`:

| File | Role |
|------|------|
| `Job_Scrape.xlsx` | Source Excel (Asset Managers, Banks sheets) |
| `companies.csv` | Normalized registry: name, category, website, career page, status |
| `companies.json` | Same registry as JSON |

**Registry fields today**

| Field | Description |
|-------|-------------|
| `company_name` | Display / join key |
| `category` | e.g. Asset Managers, Banks |
| `website` | Normalized company homepage |
| `career_page` | Resolved careers URL (empty if unresolved) |
| `career_page_status` | Probe result (`ok:200`, `fail:404`, `no_website`, …) |

**Baseline coverage (phase 1 probe)**

- 267 companies total
- 163 with reachable career pages
- 104 unresolved (no site, 404, blocked, etc.)

Unresolved rows remain in the registry and are flagged for manual fix or re-resolution; they are skipped by ingest until `career_page` is set.

---

## System components

### 1. Company registry

**Purpose:** Single source of truth for who we monitor.

**Inputs**

- Excel datasheet (`Job_Scrape.xlsx`) with company name + website
- Optional manual overrides for career URLs

**Responsibilities**

- Import / refresh companies from Excel
- Normalize websites (`https://…`)
- Persist `companies.csv` / `companies.json` (and later a DB table)
- Track career-page resolution status

**Outputs**

- List of companies eligible for weekly ingest (`career_page` present and healthy)

### 2. Career page resolver

**Purpose:** Map website → careers URL when Excel only has a homepage.

**Approach**

- Probe common patterns: `/careers`, `/jobs`, `careers.{domain}`, ATS hosts (Workday, Greenhouse, Lever, etc.)
- Record final URL + HTTP status
- Allow manual override in registry

**Outputs**

- Updated `career_page` + `career_page_status` per company

### 3. Role ingest engine

**Purpose:** Fetch open roles from each eligible career page. No full applicant ATS — read public listings only.

**Per company, each weekly run**

1. Fetch career page (HTML and/or known ATS APIs where detectable)
2. Extract job postings (title, location, URL, posted/updated date if available)
3. Deduplicate within the page and against prior snapshots
4. Emit raw + normalized posting records tagged with `run_id` / `week_id`

**Failure handling**

- Soft-fail per company (timeout, 403, empty board)
- Log status on the company run; do not abort the full weekly batch

### 4. Role classifier

**Purpose:** Keep only Riviera-relevant openings.

**In scope — functions**

- Technology, Product, Engineering, Data, AI, Machine Learning

**In scope — seniority**

- IC → Manager → Senior Manager → Head → Director → Senior Director → VP → SVP → C-level (CTO, CAIO, CPO, etc.)

**Out of scope — functions**

- Sales, Marketing, Finance, HR, Legal, Operations

**Outputs per posting**

- `function` (enum / multi-label)
- `seniority_band`
- `in_scope` (boolean)
- Optional confidence + matched title tokens for audit

Only `in_scope = true` postings feed Key Insights and the primary opportunity views.

### 5. Snapshot & change detection

**Purpose:** Turn weekly crawls into actionable deltas.

For each company and week:

| Signal | Definition |
|--------|------------|
| **New** | In-scope role present this week, absent last week |
| **Updated** | Same role identity, metadata changed (title/location/url) |
| **Removed** | Present last week, gone this week |
| **Unchanged** | Still open, no material change |

Role identity prefers stable job URL / ATS id; falls back to normalized title + company + location.

### 6. Weekly scheduler

**Purpose:** Run the full monitoring cycle once per week without manual kicks.

**Cadence:** Weekly (configurable weekday/time, e.g. Monday 06:00 local or UTC).

**Job sequence (single weekly run)**

```
1. Load company registry
2. Select companies with valid career_page
3. For each company (rate-limited concurrency):
     a. Ingest open roles
     b. Classify
     c. Diff vs previous week snapshot
     d. Persist postings + deltas + run status
4. Aggregate structured weekly deltas (new / updated / removed, rollups)
5. Call Groq LLM to generate Key Insights narratives and priorities
6. Persist WeeklyInsight (structured stats + Groq output)
7. Mark run complete (success / partial / failed counts)
8. Notify (optional): Slack / email that Key Insights are ready
```

**Scheduler properties**

| Property | Behavior |
|----------|----------|
| Trigger | Cron / managed scheduler (e.g. APScheduler, Celery Beat, GitHub Actions, cloud cron) |
| Idempotency | `week_id` (ISO week) + company; re-runs upsert rather than duplicate |
| Partial success | One company failure does not fail the week |
| Observability | Run log: started_at, finished_at, companies_ok, companies_failed, new_roles, removed_roles |
| Backfill | Support manual “run now” and single-company re-scrape |

### 7. Key Insights (weekly jobs display)

**Purpose:** Primary product surface for research / sales enablement — show what the weekly scheduler just sourced, enriched by **Groq**.

Each completed weekly run produces a **Key Insights** pack that is the default landing view after a refresh.

#### Structured inputs (from scrape + diff)

| Insight block | Content |
|---------------|---------|
| **Week summary** | Week id/date range, companies scraped, success/fail counts, total in-scope roles, new / removed / updated counts |
| **New openings this week** | List of newly detected in-scope jobs (company, title, function, seniority, location, career/job URL) |
| **Leadership & executive pulse** | Subset of new/updated roles at Head+ / Director+ / VP+ / C-level |
| **Hottest companies** | Companies with the most new in-scope postings this week |
| **Function mix** | Breakdown of new roles by Technology / Product / Engineering / Data / AI / ML |
| **Seniority mix** | IC vs manager vs leadership vs C-level among new roles |
| **Removals / cooling** | Notable in-scope roles that disappeared (optional signal for filled or closed searches) |
| **Coverage gaps** | Companies skipped (missing career page, scrape failure) needing attention |

### 8. Groq LLM insights layer

**Purpose:** Convert structured weekly job deltas into recruiter-ready intelligence using the **Groq API**.

Groq is the designated LLM provider for insight generation. It does **not** replace scraping or deterministic classification; it operates on the post-diff weekly payload.

#### When Groq runs

At the end of each weekly scheduler run, after JobDelta + rollups are persisted:

1. Assemble a compact, structured context pack (new roles, leadership roles, company rollups, removals, coverage gaps)
2. Send that pack to Groq with a fixed system prompt for Riviera search enablement
3. Persist Groq’s structured response on `WeeklyInsight`
4. Render it in the Key Insights UI alongside the raw job lists

#### What Groq produces

| Output | Description |
|--------|-------------|
| **Executive brief** | Short week-level summary of hiring signal across the tracked set |
| **Priority companies** | Ranked companies worth outreach this week, with rationale tied to specific postings |
| **Role-level callouts** | Highlighted new openings (esp. Head+ / VP+ / C-level) and why they matter for search |
| **Outreach angles** | Suggested talking points / timing per priority company or role cluster |
| **Risk / noise notes** | Caveats (e.g. evergreen boards, thin signal, scrape gaps) so researchers don’t over-index |

#### Design rules

- **Grounding:** Prompts must require citations to company names + job titles/URLs from the input pack; no invented openings
- **Deterministic core, LLM shell:** Counts, lists, and diffs stay code-computed; Groq adds narrative, ranking explanation, and outreach framing
- **Model config:** Model id, temperature, and max tokens live in config (env); default to a fast Groq chat/completions model suitable for weekly batch size
- **Failure mode:** If Groq is unavailable, still publish structured Key Insights (lists + rollups); mark `llm_status = failed` and allow retry without re-scraping
- **Cost / latency:** One (or few) batched Groq calls per weekly run — not one call per job — unless a company deep-dive is requested later

#### UX principles

- Key Insights is **week-scoped**: default = latest completed weekly run; user can page prior weeks
- Show Groq brief + priorities at the top; job tables underneath as evidence
- Every job row links back to source career/job URL and shows first-seen timestamp
- Highlight **new this week** as the primary call-to-action list (not the full historical dump)
- Full role repository remains available as a secondary “All openings” browse/search

#### Insight generation timing

Structured aggregates are computed at the **end of each weekly scheduler run**, then enriched via Groq. Both layers are stored as a snapshot so the UI does not recompute diffs or re-call the LLM on every page load.

---

## Logical data model

```
Company
  id, name, category, website, career_page, career_page_status, updated_at

ScrapeRun
  id, week_id, started_at, finished_at, status, stats_json

CompanyRun
  id, scrape_run_id, company_id, status, http_status, error, roles_found, roles_in_scope

JobPosting (current + history)
  id, company_id, external_id, title, location, job_url,
  function, seniority_band, in_scope,
  first_seen_week, last_seen_week, status (open|removed)

JobSnapshot
  id, scrape_run_id, job_posting_id, raw_payload_ref

JobDelta
  id, scrape_run_id, job_posting_id, change_type (new|updated|removed)

WeeklyInsight
  id, week_id, scrape_run_id, summary_json,
  groq_model, groq_prompt_version, llm_status,
  llm_brief, llm_priorities_json, llm_raw_response_ref,
  generated_at
```

---

## End-to-end weekly flow

```
Sunday/Monday cron fires
        │
        ▼
 Load companies.csv / DB registry
        │
        ▼
 Filter: career_page present
        │
        ▼
 Parallel ingest (N workers, polite rate limits)
        │
        ├──▶ Classify titles
        ├──▶ Upsert JobPosting
        └──▶ Write JobDelta (new / updated / removed)
        │
        ▼
 Build structured weekly aggregates
        │
        ▼
 Groq LLM: brief, priorities, outreach angles
        │
        ▼
 Persist WeeklyInsight (stats + Groq output)
        │
        ▼
 Key Insights UI shows:
   • Groq executive brief + priority companies
   • New jobs this week (primary evidence)
   • Leadership pulse
   • Company / function / seniority rollups
   • Coverage failures
```

---

## Application layers

| Layer | Responsibility |
|-------|----------------|
| **Data** | Excel import, `data/companies.*`, later Postgres (or equivalent) for runs, jobs, insights |
| **Workers** | Resolver, ingest, classifier, diff, insight aggregator |
| **LLM (Groq)** | Weekly Key Insights narratives, prioritization, outreach angles from structured deltas |
| **Scheduler** | Weekly trigger + manual re-run API/CLI |
| **API** | Companies, jobs, week insights, run status, Groq insight retry |
| **UI** | Key Insights (default), All openings, Company detail, Coverage health |

---

## Suggested tech shape (implementation-agnostic defaults)

These are starting recommendations; swap to match team stack.

| Concern | Option |
|---------|--------|
| Language | Python (scraping + scheduling ecosystem) |
| Scheduler | Cron / APScheduler / Celery Beat / cloud scheduler |
| Fetch | `httpx` + selective Playwright for JS-heavy ATS boards |
| Storage | Postgres for postings/runs; keep `data/` as seed & offline export |
| Classifier | Rules + title taxonomy first (deterministic); Groq may assist ambiguous titles later if needed |
| LLM / Insights | **Groq API** — weekly Key Insights brief, priorities, outreach angles |
| API | FastAPI (or similar) |
| UI | Web app with Key Insights as home after each weekly refresh |

---

## Non-goals (architecture boundaries)

- Candidate sourcing / resume search
- Applying to jobs or ATS write-back
- Replacing CRM
- Monitoring companies outside the provided registry
- Ingesting out-of-scope functions (Sales, Marketing, Finance, HR, Legal, Operations)

---

## Phased delivery

### Phase 0 — Done / in progress

- Problem + context docs
- Excel stored under `data/`
- Company registry with website + career page probe results

### Phase 1 — Registry hardening

- Manual fill / re-probe for unresolved career pages
- Health dashboard for coverage gaps

### Phase 2 — Ingest MVP

- Scrape eligible career pages
- Persist raw + classified in-scope roles
- No scheduler yet; manual batch run

### Phase 3 — Weekly scheduler + Key Insights (Groq)

- Cron weekly full cycle
- Diff vs prior week
- Groq-powered Key Insights: executive brief, priority companies, outreach angles
- **Key Insights** UI: Groq narrative + weekly sourced jobs, leadership pulse, rollups, coverage gaps
- Graceful fallback when Groq is down (structured insights only)

### Phase 4 — Enablement polish

- Alerts when high-seniority roles appear
- Historical week browser
- Export to Slack / CRM workflows
- Optional on-demand Groq deep-dive per company

---

## Success metrics

| Metric | Target intent |
|--------|----------------|
| Career-page coverage | Maximize share of registry with working `career_page` |
| Weekly run completion | High % companies scraped successfully each week |
| Insight freshness | Key Insights available shortly after each scheduled run |
| LLM usefulness | Groq briefs cite real postings and improve outreach prioritization |
| Signal quality | High precision on in-scope function/seniority filters |
| Time saved | Researchers stop bulk-manual career page checks |

---

## Open decisions

1. Exact weekly run day/time and timezone
2. Concurrency / rate limits per ATS domain
3. How aggressively to use headless browsers vs static HTTP
4. Whether Key Insights alerts are push (Slack) or pull (UI-only) in v1
5. Database vs file-backed storage for the first ingest MVP
6. Which Groq model id to standardize on (and temperature / max tokens)
7. Exact JSON schema for Groq insight responses (priorities, callouts, outreach angles)
