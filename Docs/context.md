# Context

## Background

Riviera Partners tracks hiring activity across a target list of 200–300 portfolio companies and technology organizations to identify executive search opportunities.

Today, researchers manually visit each company's careers page, review open positions, and identify roles relevant to the firm's search practice. This is time-consuming, difficult to scale, and prone to missed opportunities as postings change frequently.

## Goal

Automate career-page monitoring and maintain an up-to-date repository of relevant openings so research and sales enablement teams can identify client opportunities faster, reduce manual effort, and avoid missing strategic hiring signals.

## Company input

Company coverage comes from an Excel datasheet that will be provided. Each row includes:

- Company name
- Company website

The system uses these entries to locate and monitor each company's career page, then ingest open roles from that page.

## What the system does

1. Load companies from the Excel datasheet (name + website)
2. Resolve and visit each company's career page
3. Ingest open roles from those career pages
4. Filter to in-scope functions and seniority levels
5. Store results in a centralized, up-to-date repository
6. Re-run this process on a weekly schedule

## Role scope

### In scope — functions

- Technology
- Product
- Engineering
- Data
- AI
- Machine Learning

### In scope — seniority

All levels, including IC, Manager, Senior Manager, Head, Director, Senior Director, Vice President, SVP, CTO, Chief AI Officer, Chief Product Officer, and other C-level executives.

### Out of scope — functions

Sales, Marketing, Finance, HR, Legal, and Operations.

## Scheduling

A weekly scheduler runs the full ingest cycle for all companies in the datasheet:

- Scan career pages
- Extract new and updated vacancies
- Refresh the repository of relevant openings

## Desired outcome

A centralized, automatically updated database of relevant technology leadership and specialist hiring activity, refreshed weekly from the provided company list.
