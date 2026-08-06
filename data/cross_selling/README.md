# Cross-Selling data intake

Source files for Riviera’s **cross-sell** companies (`category = Cross-Selling`).

## Source

| File | Role |
|------|------|
| `Cross Sell proj.xlsx` | Original intake (company name, website, optional job-board link) |

## Generated files

| File | Purpose |
|------|---------|
| `companies.csv` / `.json` | Cross-Selling cohort → merged into `data/companies.csv` |

## Notes

- Same company name may also exist under **Top Targets** (or other cohorts). Registry uniqueness is `(name, category)`.
- Excel `Links To Jobs` are stored as `career_page_source = manual` when present.
- Companies without a job link are resolved via `rivi resolve-careers --category "Cross-Selling"`.

## How to refresh

1. Update the Excel in this folder (or point the import script at Downloads).
2. Upsert into DB with category `Cross-Selling` (preserve other-category rows).
3. `rivi resolve-careers --category "Cross-Selling"`
4. `rivi scrape --category "Cross-Selling"`
