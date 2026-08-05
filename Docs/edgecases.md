# Edge Cases

Catalog of edge cases for Rivi, derived from `Docs/architecture.md` and `Docs/implementationplan.md`. Use this during design reviews, scraper/classifier tests, and Key Insights QA.

**Handling legend**

| Tag | Meaning |
|-----|---------|
| **Skip** | Exclude from ingest this run; record reason |
| **Soft-fail** | Fail one company; continue weekly batch |
| **Flag** | Persist result but surface in Coverage / risk notes |
| **Dedupe** | Treat as same entity; upsert |
| **Exclude** | Classifier marks `in_scope = false` |
| **Fallback** | Use alternate path (structured-only insights, prior snapshot, etc.) |

---

## 1. Company registry & input data

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| R1 | Excel row missing website | Store company; `career_page` empty; **Skip** ingest; show in coverage gaps (`no_website`) |
| R2 | Invalid / malformed website (`htp://`, spaces, bare TLD) | Normalize if possible; else **Flag** `InvalidURL`; **Skip** ingest |
| R3 | Duplicate company names across sheets (e.g. parent bank + subsidiary) | Separate registry rows if websites differ; if same website, **Dedupe** on normalized domain + name |
| R4 | Same website, different display names | Prefer single company keyed by normalized domain; keep aliases |
| R5 | Excel re-import with renamed company | Upsert by stable id or normalized website; do not orphan prior `JobPosting` rows |
| R6 | Company removed from Excel | Soft-archive in registry; stop scheduling; retain historical jobs/insights |
| R7 | Manual career URL override vs auto-resolved URL | Manual override wins; mark `career_page_source = manual` |
| R8 | Category only in Excel (Asset Managers / Banks) missing later | Default `category = unknown`; still allow ingest if career page exists |
| R8a | Top Targets company already in registry under another category | Prefer `category = Top Targets` when both apply (v1 single category); keep same `JobPosting` history |
| R8b | Past opportunity row with unknown `company_name` | **Flag**; do not invent a company — fix name to match registry before import |
| R8c | Multiple past opportunities for one Top Target | One `opportunities.csv` row per search/placement; join on `company_name` |
| R9 | Tickers / suffixes in names (`NYS: BAC`) | Keep display name as-is; normalize separately for matching/search |
| R10 | Trailing whitespace / odd Unicode in names | Trim + NFKC normalize on import |

**Observed baseline:** 12/267 companies already have no website; treat as permanent **Skip** until data fixed.

---

## 2. Career page resolution

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| C1 | `/careers` returns 404 but `/jobs` works | Resolver tries path list; store first career-like success |
| C2 | URL returns 200 but redirects to homepage | **Flag** as weak match (`ok_redirect`); prefer not to ingest until verified or manual override |
| C3 | Location / region chooser interstitial (e.g. “choose your location”) | **Flag**; may need region-specific career URL or Playwright follow-through |
| C4 | Careers subdomain exists but apex `/careers` 404 | Accept `careers.{domain}` / ATS host |
| C5 | HTTP 403 / bot wall on probe | **Soft-fail** resolve; retry with browser UA / Playwright later; keep prior known-good URL if any |
| C6 | HTTP 429 rate limit during bulk probe | Back off per domain; do not wipe existing `career_page` |
| C7 | TLS / DNS failure (`URLError`) | **Soft-fail**; leave prior URL intact on re-probe |
| C8 | Geo-blocked or VPN-required careers site | **Flag** `geo_blocked`; **Skip** until operable from deploy region |
| C9 | Careers page is PDF or “email us” only | **Flag** `no_parseable_jobs`; **Skip** ingest |
| C10 | Multiple career brands (parent TIAA vs Nuveen) | Allow career host ≠ company website host; store final resolved URL |
| C11 | Short-lived marketing careers URL that rotates | Prefer stable ATS board URL when detected |
| C12 | False positive: `/join` is a newsletter signup | Require career-like final URL keywords or detectable job list markup before marking ok |

**Observed baseline:** ~104 unresolved (404, 403, timeouts, no website). Ingest must never require 100% resolution.

---

## 3. Fetch & ingest

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| I1 | Empty job board (valid page, zero roles) | Success with `roles_found = 0`; not a hard failure |
| I2 | Timeout mid-fetch | **Soft-fail** company; do not mark all prior jobs removed |
| I3 | Partial HTML / truncated response | **Soft-fail** or **Flag** low-confidence parse; avoid false mass-removals |
| I4 | JS-rendered board; static HTTP sees no jobs | Detect empty-vs-JS; queue Playwright path or **Flag** `js_required` |
| I5 | Infinite scroll / pagination | Paginate or API dump until cap; record `parse_incomplete` if capped |
| I6 | Jobs behind “Accept cookies” / consent wall | Dismiss via Playwright or cookie header; else **Soft-fail** |
| I7 | CAPTCHA / Cloudflare challenge | **Soft-fail**; surface coverage gap; do not loop retries aggressively |
| I8 | ATS API available (Greenhouse, Lever, Workday JSON) | Prefer API over HTML; same schema into `JobPosting` |
| I9 | Mixed ATS (marketing page + iframe to Workday) | Follow iframe/canonical board URL when detectable |
| I10 | Duplicate listings same title, different locations | Separate postings if URLs/locations differ |
| I11 | Duplicate listings same URL listed twice | **Dedupe** within fetch |
| I12 | Relative job links (`/jobs/123`) | Resolve against career page origin |
| I13 | Tracking query params on job URLs | Strip known tracking params for identity; keep canonical URL for display |
| I14 | Job URL requires auth / returns 401 | Store title from list page if present; **Flag** detail fetch failed |
| I15 | Extremely large board (1000+ roles) | Cap per company per run; **Flag** truncation; still classify fetched set |
| I16 | Non-English titles / pages | Ingest; classifier uses language-agnostic keywords where possible; **Flag** for review if unmatched |
| I17 | Robots.txt disallows crawl | Honor policy for v1 or **Skip** with `robots_blocked`; log explicitly |
| I18 | Site blocks datacenter IPs only | **Soft-fail**; document; consider allowlisted runner later |
| I19 | SSL cert expired on careers host | **Soft-fail**; do not disable TLS verification in prod |
| I20 | Career page OK but all jobs are contractor/vendor spam | Classifier / filters handle; do not special-case at fetch |

**Critical:** On ingest **Soft-fail**, never treat “missing this week” as **Removed** for that company. Only diff removals when the company run status is success.

---

## 4. Role classification

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| F1 | Ambiguous title (“Director of Operations”) | **Exclude** (Operations out of scope) |
| F2 | “Sales Engineer” / “Solutions Engineer” (sales-leaning) | Prefer **Exclude** unless clearly product/engineering IC; tune via tests |
| F3 | “Product Marketing Manager” | **Exclude** (Marketing) |
| F4 | “Financial Engineer” / “Quant Developer” at asset manager | Treat as Engineering/Technology **in scope** if engineering signal clear; else **Flag** for review |
| F5 | “Data Entry” / “Data Analyst (Finance Ops)” | Exclude entry/ops; include true Data/Analytics/DS/ML |
| F6 | “AI Product Manager” | In scope (Product + AI); seniority from PM band |
| F7 | “Head of People Technology” / HRIS | Prefer **Exclude** (HR) unless pure engineering platform role with strong eng tokens |
| F8 | “CTO” / “Chief AI Officer” / “CPO” | In scope C-level |
| F9 | “CEO” / “CFO” / “COO” / “CHRO” / “CLO” | **Exclude** (not Tech/Product/Data/AI leadership for this product) |
| F10 | “VP Engineering, Sales” or dual-function titles | In scope if any primary in-scope function token dominates |
| F11 | Intern / co-op / apprentice engineering roles | Configurable: default include as IC or exclude via `exclude_interns` flag |
| F12 | “Manager” without function (“Office Manager”) | **Exclude** |
| F13 | Seniority inflation (“Senior Senior”, “Staff II”) | Map to nearest band; do not invent new bands |
| F14 | “Principal” / “Distinguished” / “Fellow” | Map to IC (senior IC), not Director, unless title says Director |
| F15 | “Head of” vs “Director of” vs “VP of” same function | Distinct seniority bands as architecture defines |
| F16 | All-caps / punctuation-heavy titles | Normalize before match |
| F17 | Title is only “Engineer” with department in another field | Use department/team metadata when present |
| F18 | Multi-label (ML Engineer on Product team) | Allow multi-label; `in_scope = true` if any in-scope function matches and no hard exclusion |
| F19 | False in-scope leaks into Key Insights | Insights and rollups use `in_scope = true` only; keep out-of-scope in raw store for audit |
| F20 | No keyword match | `in_scope = false`; optional `unclassified` flag for sampling |

---

## 5. Identity, snapshots & change detection

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| D1 | Same job, URL changed (ATS migration) | May appear removed + new; **Flag** possible remaps via title+company fuzzy match (v2) |
| D2 | Same URL, title edited slightly | **Updated**, not new |
| D3 | Evergreen posting (always open, “posted today” resets) | Still one identity; do not treat daily refresh as new every week |
| D4 | Job closed then reposted same URL | If seen gap across successful runs: removed then new (or reopen status) |
| D5 | First-ever scrape for a company | All current in-scope roles are **New** for that week (expected); Groq risk note: “baseline week” |
| D6 | Company failed last week, succeeds this week | Do not mark everything new vs failed week; diff against last **successful** company snapshot |
| D7 | Company succeeds with 0 jobs after previously having jobs | Valid **Removed** for prior in-scope roles |
| D8 | Timezone straddling ISO week boundary | `week_id` uses configured timezone consistently |
| D9 | Location-only change | **Updated** |
| D10 | Duplicate identity collision (fallback key too weak) | Prefer URL/external_id; tighten fallback; **Dedupe** on conflict |
| D11 | Partial scrape then “removals” | Forbidden — see I2/I3; only diff on full success |
| D12 | Re-run same `week_id` | Upsert deltas; no duplicate `JobPosting` rows |

---

## 6. Weekly scheduler & runs

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| S1 | Scheduler fires while previous run still active | Reject overlapping run or queue; one active `ScrapeRun` max |
| S2 | Process crash mid-run | Run status `failed`/`partial`; next run continues; no corrupt “all removed” |
| S3 | Manual `run-weekly` same ISO week as cron | Idempotent upsert |
| S4 | Manual single-company re-scrape mid-week | Updates that company; optional insight regen without full re-scrape |
| S5 | Zero eligible companies | Complete run with empty insights; **Flag** coverage |
| S6 | All companies soft-fail | `ScrapeRun` status `failed`; do not call Groq with empty/meaningless pack (or call with coverage-only risk notes) |
| S7 | Clock jump / DST | Cron expression + timezone library; document run window |
| S8 | Deploy during scheduled window | Missed run: allow catch-up CLI; do not double-send alerts |
| S9 | Concurrency overwhelms one ATS domain | Per-domain rate limit; remaining companies still process |
| S10 | Partial success (mixed ok/fail) | Status `partial`; Key Insights built from successful companies only; list failures in coverage gaps |

---

## 7. Groq LLM insights

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| G1 | Groq API down / 5xx | **Fallback**: publish structured insights; `llm_status = failed`; allow regenerate |
| G2 | Invalid API key / quota exceeded | Same as G1; alert ops |
| G3 | Model returns non-JSON / schema violation | Retry once; then **Fallback**; store raw response for debug |
| G4 | Model invents a job not in the pack | Validator drops ungounded items; **Flag** in risk notes if many drops |
| G5 | Model cites wrong company for a title | Reject that callout; keep grounded subset |
| G6 | Empty new-roles week (quiet week) | Brief should say thin signal; priorities may be empty; not an error |
| G7 | Huge week exceeds context window | Truncate pack by priority (leadership first, then hottest companies); note truncation in prompt + risk notes |
| G8 | Prompt version changed | Store `groq_prompt_version`; regenerating may differ from historical brief |
| G9 | Latency timeout | **Fallback**; regenerate later |
| G10 | Temperature / nondeterminism | Accept variance in prose; structured priorities must still be grounded |
| G11 | User regenerates insights after fixing classifier | Allowed without re-scrape; overwrite LLM fields only |
| G12 | UI shows Groq brief without evidence tables | Forbidden UX — always show source job lists alongside |

---

## 8. Key Insights UI & product

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| U1 | No weekly run yet | Empty state: “No insights yet — run scrape / wait for schedule” |
| U2 | Latest run partial | Banner: partial coverage; show failures count |
| U3 | `llm_status = failed` | Show structured blocks; banner “AI brief unavailable — retry” |
| U4 | User selects prior week | Load that week’s snapshot; do not live-recompute |
| U5 | Broken job URL in table | Still show row; link may 404 (external truth changed) |
| U6 | Very long title / company name | Truncate in table; full text on detail/hover |
| U7 | Hottest companies tie | Stable sort (name or total roles) |
| U8 | Leadership pulse empty but many IC roles | Show empty pulse; brief should not claim executive hiring |
| U9 | Stale “latest” if cron missed | Show last completed week + “as of” timestamp |
| U10 | All openings view includes out-of-scope | Filter default in-scope; optional toggle for audit |

---

## 9. Storage & data integrity

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| DB1 | SQLite locked under concurrent writers | Serialize writers or move to Postgres before multi-worker prod |
| DB2 | Migration mid-run | Block runs during migrate |
| DB3 | CSV and DB drift | DB is source of truth after Phase 1; export CSV from DB |
| DB4 | Delete company with history | Soft-delete; keep postings for audit |
| DB5 | Null external_id and null-ish title | Reject persist; **Soft-fail** parse quality |

---

## 10. Notifications (Phase 4)

| ID | Edge case | Expected behavior |
|----|-----------|-------------------|
| N1 | Alert on baseline first week (everything “new”) | Suppress or mark “initial baseline — not net-new market signal” |
| N2 | Duplicate alert on week re-run | Dedupe by `week_id` + alert type |
| N3 | Alert channel down | Log failure; insights still available in UI |
| N4 | No high-seniority roles | Skip seniority alert; still optional “week ready” ping |

---

## Cross-cutting rules (always)

1. **Soft-fail per company** — never abort the full weekly batch for one site.  
2. **No removal inference on failed scrapes** — protects against false “cooling” signals.  
3. **Deterministic counts, LLM narrative** — rollups from DB; Groq does not own totals.  
4. **Grounded Groq only** — every callout must map to an input posting.  
5. **Idempotent `week_id`** — safe retries.  
6. **Coverage gaps are first-class** — missing career pages and scrape failures appear in Key Insights every week.

---

## Suggested test fixtures

Build fixture packs for CI from this list:

- Registry: missing website, bad URL, duplicate domain  
- Resolver: 404 paths, redirect-to-home, 403, careers subdomain  
- Ingest: empty board, paginated Greenhouse JSON, JS-empty HTML, timeout  
- Classifier: F1–F15 title strings  
- Diff: first week baseline, failed-then-success week, evergreen URL, title edit  
- Groq: invalid JSON, ungrounded job, empty new-roles week, oversize pack  
- Scheduler: overlapping run, partial success, zero eligible companies  

---

## Priority to handle in v1

Must-handle before trusting Key Insights:

| Priority | IDs |
|----------|-----|
| P0 | I2, I3, D6, D11, S1, S6, S10, G1, G4, R1, C2 |
| P1 | I4, I7, I8, F1–F9, D1, D5, G6, G7, U1–U3 |
| P2 | Remaining rows; Phase 4 notification cases |
