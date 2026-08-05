# Top Targets data intake

Source files for Riviera’s **top client** companies (`category = Top Targets`) and past search/placement history.

See `Docs/top-targets.md` for the full plan.

## Source

| File | Role |
|------|------|
| `Multi-year Public+PE-backed Placements_Jul 2026.xlsx` | Original CRM export (Jul 2026) |
| Sheet `Public+PE-backed` | Canonical placement rows used for import |

## Generated files

| File | Purpose |
|------|---------|
| `companies.csv` / `.json` | 102 companies → merged into `data/companies.csv` |
| `opportunities.csv` / `.json` | 629 past placements (relationship context) |

## Stats (Jul 2026 load)

- **102** Top Target companies
- **629** placements (all `Search Stage = Placement`)
- Years: **2008–2026**
- Overlap with Startups registry: **Hulu** (retagged to Top Targets; career page preserved)

## How to refresh

1. Drop an updated Excel into this folder (or point the import script at Downloads).
2. Re-run the parse/merge into `data/companies.csv`.
3. `rivi import-companies --csv data/companies.csv`
4. Resolve careers → `rivi scrape --category "Top Targets"`

Do **not** put scraped job openings here; those come from the career-page scrape pipeline into the main DB.
