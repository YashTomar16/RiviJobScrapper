from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """Repo root: .../Rivi (parent of src/)."""
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.2
    groq_max_tokens: int = 4096

    database_url: str = "sqlite:///./data/rivi.db"

    rivi_data_dir: Path | None = None
    rivi_logs_dir: Path | None = None
    rivi_companies_csv: Path | None = None

    weekly_cron: str = "0 6 * * 1"
    weekly_timezone: str = "UTC"

    scrape_concurrency: int = 5
    scrape_timeout_seconds: int = 30
    scrape_domain_delay_seconds: float = 0.5
    scrape_respect_robots: bool = True
    resolve_timeout_seconds: float = 8.0
    resolve_concurrency: int = 10

    # Alerts (Phase 4)
    slack_webhook_url: str = ""
    alert_email_to: str = ""
    alert_email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_tls: bool = True
    alerts_enabled: bool = True

    # Basic auth for UI when exposed beyond localhost
    basic_auth_user: str = ""
    basic_auth_password: str = ""

    log_level: str = "INFO"

    @property
    def data_dir(self) -> Path:
        if self.rivi_data_dir is not None:
            return Path(self.rivi_data_dir)
        return project_root() / "data"

    @property
    def logs_dir(self) -> Path:
        if self.rivi_logs_dir is not None:
            return Path(self.rivi_logs_dir)
        return project_root() / "logs"

    @property
    def companies_csv(self) -> Path:
        if self.rivi_companies_csv is not None:
            return Path(self.rivi_companies_csv)
        return self.data_dir / "companies.csv"

    @property
    def companies_excel(self) -> Path:
        return self.data_dir / "Job_Scrape.xlsx"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def runs_dir(self) -> Path:
        return self.logs_dir / "runs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
