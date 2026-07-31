from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from rivi import __version__
from rivi.companies import (
    export_companies_csv,
    export_companies_json,
    import_from_csv,
    import_from_excel,
    set_career_page_manual,
    set_company_skip,
    write_import_report,
)
from rivi.config import get_settings
from rivi.coverage import build_coverage_report, write_coverage_json, write_coverage_markdown
from rivi.db import session_scope
from rivi.logging_setup import new_run_log_path, setup_logging
from rivi.resolver import resolve_careers

app = typer.Typer(
    name="rivi",
    help="Rivi — career-page monitoring and weekly Key Insights.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _sync_exports(session) -> None:
    settings = get_settings()
    n = export_companies_csv(session, settings.companies_csv)
    export_companies_json(session, settings.data_dir / "companies.json")
    console.print(f"[dim]Synced CSV/JSON export ({n} rows) → {settings.companies_csv}[/dim]")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG logging"),
) -> None:
    """Rivi CLI."""
    settings = get_settings()
    if verbose:
        settings.log_level = "DEBUG"
    setup_logging(settings)


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    console.print(__version__)


@app.command("import-companies")
def import_companies_cmd(
    csv_path: Optional[Path] = typer.Option(
        None,
        "--csv",
        help="Path to companies CSV (default: data/companies.csv)",
    ),
    excel_path: Optional[Path] = typer.Option(
        None,
        "--excel",
        help="Import/refresh from Excel (name, category, website only)",
    ),
    write_report: bool = typer.Option(
        True,
        "--write-report/--no-write-report",
        help="Write structured JSON under logs/runs/",
    ),
) -> None:
    """Upsert companies into the DB from CSV and/or Excel; sync CSV export."""
    settings = get_settings()
    logger = setup_logging(settings)

    if excel_path is None and csv_path is None:
        # Default: seed/refresh from CSV registry
        csv_path = settings.companies_csv

    with session_scope(settings) as session:
        if excel_path is not None:
            path = excel_path
            logger.info("Importing companies from Excel %s", path)
            result = import_from_excel(session, path)
        else:
            assert csv_path is not None
            path = csv_path
            logger.info("Importing companies from CSV %s", path)
            result = import_from_csv(session, path)

        table = Table(title="Company registry import → DB")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Source", result.source)
        table.add_row("Rows processed", str(result.total))
        table.add_row("Inserted", str(result.inserted))
        table.add_row("Updated", str(result.updated))
        table.add_row("With website", str(result.with_website))
        table.add_row("With career page", str(result.with_career_page))
        table.add_row("Missing website", str(result.missing_website))
        table.add_row("Missing career page", str(result.missing_career_page))
        console.print(table)

        cat = Table(title="By category")
        cat.add_column("Category")
        cat.add_column("Count", justify="right")
        for name, count in sorted(result.by_category.items()):
            cat.add_row(name, str(count))
        console.print(cat)

        _sync_exports(session)

        if write_report:
            report_path = new_run_log_path("import-companies", settings)
            write_import_report(result, report_path)
            console.print(f"[green]Wrote run report[/green] {report_path}")
            logger.info("Wrote import report to %s", report_path)

    console.print(
        f"[green]OK[/green] DB upsert complete "
        f"({result.inserted} inserted, {result.updated} updated)."
    )


@app.command("resolve-careers")
def resolve_careers_cmd(
    company: Optional[str] = typer.Option(None, "--company", help="Resolve a single company"),
    missing_only: bool = typer.Option(
        True,
        "--missing-only/--all",
        help="Only companies without a career_page (default)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-resolve even when career_page exists (does not override manual unless combined)",
    ),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Parallel probes"),
) -> None:
    """Resolve career page URLs from company websites (improved ATS patterns)."""
    settings = get_settings()
    logger = setup_logging(settings)
    workers = concurrency or settings.resolve_concurrency

    with session_scope(settings) as session:
        try:
            summary = resolve_careers(
                session,
                company_name=company,
                missing_only=missing_only and not force,
                force=force,
                concurrency=workers,
                timeout=float(settings.resolve_timeout_seconds),
            )
        except LookupError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

        table = Table(title="Career page resolution")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Targeted", str(summary["targeted"]))
        table.add_row("Updated", str(summary["updated"]))
        table.add_row("Found", str(summary["found"]))
        table.add_row("Still missing", str(summary["still_missing"]))
        console.print(table)

        _sync_exports(session)
        report_path = new_run_log_path("resolve-careers", settings)
        report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote run report[/green] {report_path}")
        logger.info("Resolve summary: %s", {k: summary[k] for k in ("targeted", "found", "still_missing")})

    console.print("[green]OK[/green] Career resolution finished.")


@app.command("set-career-page")
def set_career_page_cmd(
    company: str = typer.Option(..., "--company", help="Exact company name"),
    url: Optional[list[str]] = typer.Option(
        None,
        "--url",
        help="Careers / jobs URL (repeat for multiple boards; stored pipe-separated)",
    ),
) -> None:
    """Manually set a company's career page (wins over auto-resolve)."""
    settings = get_settings()
    setup_logging(settings)
    urls = [u.strip() for u in (url or []) if u and u.strip()]
    if not urls:
        console.print("[red]Provide at least one --url[/red]")
        raise typer.Exit(code=2)
    combined = " | ".join(urls)
    with session_scope(settings) as session:
        try:
            row = set_career_page_manual(session, company, combined)
            name, career = row.name, row.career_page
        except LookupError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e
        _sync_exports(session)
    console.print(
        f"[green]OK[/green] Manual career page for [cyan]{name}[/cyan]:\n  {career}"
    )


@app.command("skip-company")
def skip_company_cmd(
    company: str = typer.Option(..., "--company", help="Exact company name"),
    reason: str = typer.Option("", "--reason", help="Why this company is skipped"),
    unskip: bool = typer.Option(False, "--unskip", help="Clear skip flag"),
) -> None:
    """Mark a company skipped (or clear skip) for ingest."""
    settings = get_settings()
    setup_logging(settings)
    with session_scope(settings) as session:
        try:
            row = set_company_skip(session, company, skip=not unskip, reason=reason)
            name = row.name
        except LookupError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e
        _sync_exports(session)
    state = "unskipped" if unskip else "skipped"
    console.print(f"[green]OK[/green] {name} {state}.")


@app.command("coverage-report")
def coverage_report_cmd(
    write_files: bool = typer.Option(
        True,
        "--write-files/--no-write-files",
        help="Write markdown + JSON under data/reports/",
    ),
) -> None:
    """Print coverage health and optionally write data/reports/coverage.md."""
    settings = get_settings()
    setup_logging(settings)

    with session_scope(settings) as session:
        report = build_coverage_report(session)

    table = Table(title="Coverage health")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total", str(report.total))
    table.add_row("Eligible for ingest", str(report.eligible))
    table.add_row("With career page", str(report.with_career_page))
    table.add_row("Missing career page", str(report.missing_career_page))
    table.add_row("Missing website", str(report.missing_website))
    table.add_row("Skipped", str(report.skipped))
    console.print(table)

    cat = Table(title="By category")
    cat.add_column("Category")
    cat.add_column("Total", justify="right")
    cat.add_column("Eligible", justify="right")
    cat.add_column("Missing career", justify="right")
    for name, stats in report.by_category.items():
        cat.add_row(
            name,
            str(stats["total"]),
            str(stats["eligible"]),
            str(stats["missing_career"]),
        )
    console.print(cat)

    if write_files:
        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        md_path = settings.reports_dir / "coverage.md"
        json_path = settings.reports_dir / "coverage.json"
        write_coverage_markdown(report, md_path)
        write_coverage_json(report, json_path)
        console.print(f"[green]Wrote[/green] {md_path}")
        console.print(f"[green]Wrote[/green] {json_path}")

    console.print(
        "\n[bold]Fix unresolved:[/bold]\n"
        '  rivi set-career-page --company "Name" --url "https://..."\n'
        '  rivi skip-company --company "Name" --reason "No public board"\n'
        "  rivi coverage-report"
    )


@app.command("scrape")
def scrape_cmd(
    company: Optional[str] = typer.Option(None, "--company", help="Single company name"),
    all_eligible: bool = typer.Option(False, "--all-eligible", help="Scrape all eligible companies"),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Scrape first N eligible companies (pilot)",
    ),
    use_playwright: bool = typer.Option(
        False,
        "--playwright",
        help="Use Playwright for JS-rendered boards when HTML yields no jobs",
    ),
    export: bool = typer.Option(
        True,
        "--export/--no-export",
        help="Write in-scope jobs JSON/CSV under data/reports/",
    ),
) -> None:
    """Scrape open roles from career pages, classify, and persist."""
    from rivi.ingest.runner import export_run, run_scrape

    settings = get_settings()
    logger = setup_logging(settings)

    if not company and not all_eligible and limit is None:
        console.print("[red]Specify --company, --all-eligible, or --limit[/red]")
        raise typer.Exit(code=2)

    with session_scope(settings) as session:
        try:
            summary = run_scrape(
                session,
                company_name=company,
                all_eligible=all_eligible,
                limit=limit,
                use_playwright=use_playwright,
                settings=settings,
            )
        except (LookupError, ValueError) as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

        table = Table(title=f"Scrape run #{summary['scrape_run_id']}")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Week", summary["week_id"])
        table.add_row("Status", summary["status"])
        table.add_row("Companies targeted", str(summary["companies_targeted"]))
        table.add_row("OK", str(summary["companies_ok"]))
        table.add_row("Failed", str(summary["companies_failed"]))
        table.add_row("Roles found", str(summary["roles_found"]))
        table.add_row("In-scope roles", str(summary["roles_in_scope"]))
        table.add_row("New", str(summary.get("new_roles", 0)))
        table.add_row("Updated", str(summary.get("updated_roles", 0)))
        table.add_row("Removed", str(summary.get("removed_roles", 0)))
        console.print(table)

        detail = Table(title="Per company")
        detail.add_column("Company")
        detail.add_column("Status")
        detail.add_column("Parser")
        detail.add_column("Roles", justify="right")
        detail.add_column("In-scope", justify="right")
        detail.add_column("Error")
        for row in summary.get("companies", []):
            detail.add_row(
                row["company"][:40],
                row["status"],
                row.get("parser") or "—",
                str(row["roles_found"]),
                str(row["roles_in_scope"]),
                (row.get("error") or "")[:40],
            )
        console.print(detail)

        report_path = new_run_log_path("scrape", settings)
        report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote run report[/green] {report_path}")

        if export:
            json_path, csv_path = export_run(
                session,
                summary["scrape_run_id"],
                settings.reports_dir,
                in_scope_only=True,
            )
            console.print(f"[green]Exported in-scope jobs[/green] {json_path}")
            console.print(f"[green]Exported in-scope jobs[/green] {csv_path}")

        logger.info(
            "Scrape run %s finished status=%s in_scope=%s",
            summary["scrape_run_id"],
            summary["status"],
            summary["roles_in_scope"],
        )

    console.print("[green]OK[/green] Scrape finished.")


@app.command("run-weekly")
def run_weekly_cmd(
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Limit eligible companies (pilot); default = all eligible",
    ),
    use_playwright: bool = typer.Option(
        False,
        "--playwright",
        help="Enable Playwright fallback for JS boards",
    ),
    skip_groq: bool = typer.Option(
        False,
        "--skip-groq",
        help="Persist structured insights only (no Groq call)",
    ),
    skip_alerts: bool = typer.Option(
        False,
        "--skip-alerts",
        help="Skip Slack/email high-seniority alerts",
    ),
) -> None:
    """Run the full weekly ingest → diff → Groq insights pipeline."""
    from rivi.weekly import run_weekly

    settings = get_settings()
    logger = setup_logging(settings)

    with session_scope(settings) as session:
        try:
            result = run_weekly(
                session,
                settings=settings,
                limit=limit,
                use_playwright=use_playwright,
                skip_groq=skip_groq,
                skip_alerts=skip_alerts,
                trigger="manual",
            )
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

        scrape = result["scrape"]
        table = Table(title=f"Weekly run {result['week_id']}")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Scrape run", str(scrape["scrape_run_id"]))
        table.add_row("Status", scrape["status"])
        table.add_row("Companies OK", str(scrape["companies_ok"]))
        table.add_row("Companies failed", str(scrape["companies_failed"]))
        table.add_row("New roles", str(scrape["new_roles"]))
        table.add_row("Updated roles", str(scrape["updated_roles"]))
        table.add_row("Removed roles", str(scrape["removed_roles"]))
        table.add_row("In-scope roles", str(scrape["roles_in_scope"]))
        table.add_row("LLM status", str(result["insights"]["llm_status"]))
        alerts = result.get("alerts") or {}
        table.add_row("Alerts", str(alerts.get("slack") or alerts.get("reason") or "—"))
        console.print(table)

        report_path = new_run_log_path("run-weekly", settings)
        report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote run report[/green] {report_path}")
        logger.info("Weekly run finished: %s", result)

    console.print(
        "[green]OK[/green] Weekly pipeline finished. "
        "View Key Insights: [cyan]rivi serve[/cyan] → http://127.0.0.1:8000/"
    )


@app.command("generate-insights")
def generate_insights_cmd(
    week: Optional[str] = typer.Option(
        None,
        "--week",
        help="ISO week id, e.g. 2026-W31 (default: current week)",
    ),
    skip_groq: bool = typer.Option(
        False,
        "--skip-groq",
        help="Rebuild structured aggregates only",
    ),
    regenerate: bool = typer.Option(
        False,
        "--regenerate",
        help="Re-call Groq only (no scrape); uses stored/rebuilt pack",
    ),
) -> None:
    """Generate or regenerate Groq Key Insights for a week."""
    from rivi.insights.generate import generate_insights, regenerate_llm_only
    from rivi.week import current_week_id

    settings = get_settings()
    logger = setup_logging(settings)
    week_id = week or current_week_id(settings.weekly_timezone)

    with session_scope(settings) as session:
        try:
            if regenerate:
                result = regenerate_llm_only(session, week_id, settings)
            else:
                result = generate_insights(
                    session,
                    week_id=week_id,
                    settings=settings,
                    call_llm=not skip_groq,
                )
        except LookupError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

        table = Table(title=f"Insights {result['week_id']}")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Insight id", str(result.get("insight_id")))
        table.add_row("LLM status", str(result.get("llm_status")))
        if result.get("error"):
            table.add_row("Error", str(result["error"])[:60])
        console.print(table)

        report_path = new_run_log_path("generate-insights", settings)
        slim = {k: v for k, v in result.items() if k != "aggregates"}
        report_path.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]Wrote run report[/green] {report_path}")
        logger.info("Insights %s llm_status=%s", week_id, result.get("llm_status"))

    console.print("[green]OK[/green] Insights generation finished.")


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    with_scheduler: bool = typer.Option(
        False,
        "--scheduler/--no-scheduler",
        help="Also start APScheduler for WEEKLY_CRON",
    ),
) -> None:
    """Start Key Insights UI + API (uvicorn)."""
    import uvicorn

    from rivi.web.app import create_app

    settings = get_settings()
    setup_logging(settings)
    console.print(
        f"Starting Rivi at [cyan]http://{host}:{port}/[/cyan] "
        f"(scheduler={'on' if with_scheduler else 'off'})"
    )
    application = create_app(enable_scheduler=with_scheduler)
    uvicorn.run(application, host=host, port=port, log_level=settings.log_level.lower())


@app.command("export-week")
def export_week_cmd(
    week: Optional[str] = typer.Option(
        None,
        "--week",
        help="ISO week id (default: current week)",
    ),
) -> None:
    """Export week pack JSON + CSV for CRM / BD."""
    from rivi.export import export_week_pack
    from rivi.week import current_week_id

    settings = get_settings()
    setup_logging(settings)
    week_id = week or current_week_id(settings.weekly_timezone)

    with session_scope(settings) as session:
        try:
            json_path, csv_path = export_week_pack(session, week_id, settings=settings)
        except LookupError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

    console.print(f"[green]Wrote[/green] {json_path}")
    console.print(f"[green]Wrote[/green] {csv_path}")


@app.command("send-alerts")
def send_alerts_cmd(
    week: Optional[str] = typer.Option(None, "--week", help="ISO week id"),
    force: bool = typer.Option(False, "--force", help="Re-send even if already sent"),
) -> None:
    """Send high-seniority (Head+) alerts for a week via Slack/email."""
    from rivi.alerts import dispatch_seniority_alerts
    from rivi.week import current_week_id

    settings = get_settings()
    setup_logging(settings)
    week_id = week or current_week_id(settings.weekly_timezone)

    with session_scope(settings) as session:
        result = dispatch_seniority_alerts(
            session, week_id=week_id, settings=settings, force=force
        )

    table = Table(title=f"Alerts {week_id}")
    table.add_column("Field")
    table.add_column("Value")
    for k, v in result.items():
        table.add_row(k, str(v)[:80])
    console.print(table)


@app.command("deep-dive")
def deep_dive_cmd(
    company: str = typer.Option(..., "--company", help="Company name"),
) -> None:
    """On-demand Groq deep-dive for one company (no re-scrape)."""
    from rivi.insights.deep_dive import company_deep_dive

    settings = get_settings()
    setup_logging(settings)

    with session_scope(settings) as session:
        try:
            result = company_deep_dive(session, company, settings=settings)
        except LookupError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e

    console.print(f"Company: [cyan]{result['company']}[/cyan]")
    console.print(f"LLM status: {result['llm_status']}")
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
    groq = result.get("groq") or {}
    if groq.get("executive_brief"):
        console.print("\n[bold]Brief[/bold]")
        console.print(groq["executive_brief"])
    if result.get("raw_ref"):
        console.print(f"\n[dim]Saved {result['raw_ref']}[/dim]")
