# Top Targets cohort

Plan for adding Riviera’s **top client companies** into Rivi under the registry category **`Top Targets`**, with past search/placement context, then scraping their career pages for in-scope roles.

## Status (loaded Jul 2026)

| Metric | Value |
|--------|-------|
| Source | `data/top_targets/Multi-year Public+PE-backed Placements_Jul 2026.xlsx` |
| Companies | **102** (`category = Top Targets`) |
| Past placements | **629** |
| Year span | 2008–2026 |
| Registry total | 201 (99 Startups + 102 Top Targets) |
| **Ready to scrape** | **94 / 102** |
| **Need manual career URL** | **8** |

Coverage detail: `data/reports/top_targets_career_coverage.md`

Next: scrape ready set with `rivi scrape --category "Top Targets"`, and patch the 13 manual URLs via `rivi set-career-page`.

## Why this cohort


Existing registry companies are mostly **Startups** (prospect / coverage list). **Top Targets** are known clients where Riviera already has relationship history. Past opportunities help researchers prioritize outreach when new in-scope roles appear.

## Category tag

| Field | Value |
|-------|--------|
| `category` | `Top Targets` |

Use this exact string so CLI filters work:

```bash
rivi scrape --category "Top Targets"
rivi coverage-report   # rolls up by category
```

Companies already in the registry under another category (e.g. Startups) that are also top clients should be **re-tagged** to `Top Targets` (or given a second label later if multi-tag is added). For v1: one category per company; prefer `Top Targets` when both apply.

## Input you will provide

Per company:

1. **Company name** (exact display name)
2. **Website** (homepage) — preferred; if missing we resolve later
3. **Past opportunities** — one or more searches/placements Riviera has done with that client

Optional but useful: career page URL if you already know it.

### Opportunity fields (intake)

| Field | Required | Notes |
|-------|----------|--------|
| `company_name` | Yes | Must match registry name |
| `opportunity_title` | Yes | Role / search name (e.g. “VP Engineering”) |
| `function` | No | Tech / Product / Eng / Data / AI / ML if known |
| `seniority` | No | IC / Director / VP / C-level, etc. |
| `year` or `date` | No | When the search ran or closed |
| `outcome` | No | Placed / retained / closed-no-hire / ongoing |
| `notes` | No | Free text for BD context |

## File layout

```
data/top_targets/
  README.md                 # how to fill and import
  companies.csv             # intake → merges into data/companies.csv
  opportunities.csv         # past Riviera work (not scraped jobs)
```

After intake is filled and reviewed:

1. Merge `data/top_targets/companies.csv` into the main registry (`category = Top Targets`)
2. Keep opportunities in `data/top_targets/opportunities.csv` (source of truth for relationship history)
3. Resolve career pages → scrape with `--category "Top Targets"`
4. Classify with the same in-scope rules as the rest of Rivi

## Workflow (after data arrives)

```
You paste / attach company + opportunity list
        │
        ▼
 Fill data/top_targets/companies.csv + opportunities.csv
        │
        ▼
 Upsert into DB / data/companies.csv (category = Top Targets)
        │
        ▼
 rivi resolve-careers  (or manual set-career-page)
        │
        ▼
 rivi scrape --category "Top Targets"
        │
        ▼
 Classify → Key Insights / Jobs UI (filterable by category)
```

## What stays the same

- In-scope functions and seniority (see `Docs/problemstatement.md`)
- Soft-fail per company; no invented jobs
- Groq insights still cite scraped postings only — past opportunities are **context**, not job evidence

## What is new (later code, after intake)

| Item | Status |
|------|--------|
| Registry category `Top Targets` | Ready via existing `category` field |
| `data/top_targets/` intake files | Templates ready |
| DB / UI surface for past opportunities | Deferred until intake data exists |
| Scrape + classify Top Targets | After companies have `career_page` |

## Open intake questions (answer when sending data)

1. Approximate company count?
2. Prefer paste in chat, Excel, or CSV?
3. Opportunity grain: one row per past search, or free-text list per company?
4. Any companies already in `data/companies.csv` that should flip to Top Targets?
