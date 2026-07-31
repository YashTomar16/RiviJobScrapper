from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(128), default="", index=True)
    website: Mapped[str] = mapped_column(String(1024), default="")
    career_page: Mapped[str] = mapped_column(Text, default="")
    career_page_status: Mapped[str] = mapped_column(String(128), default="")
    career_page_source: Mapped[str] = mapped_column(String(32), default="")
    skip: Mapped[bool] = mapped_column(Boolean, default=False)
    skip_reason: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    job_postings: Mapped[list[JobPosting]] = relationship(back_populates="company")

    @property
    def is_eligible(self) -> bool:
        return bool(self.career_page) and not self.skip and self.career_page_status.startswith(
            ("ok", "manual")
        )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_id: Mapped[str] = mapped_column(String(16), index=True, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running|success|partial|failed
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    trigger: Mapped[str] = mapped_column(String(64), default="manual")

    company_runs: Mapped[list[CompanyRun]] = relationship(back_populates="scrape_run")


class CompanyRun(Base):
    __tablename__ = "company_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # success|failed|skipped
    http_status: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    roles_found: Mapped[int] = mapped_column(Integer, default=0)
    roles_in_scope: Mapped[int] = mapped_column(Integer, default=0)
    parser: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scrape_run: Mapped[ScrapeRun] = relationship(back_populates="company_runs")
    company: Mapped[Company] = relationship()


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("company_id", "identity_key", name="uq_company_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(512), default="", index=True)
    identity_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), default="")
    location: Mapped[str] = mapped_column(String(512), default="")
    job_url: Mapped[str] = mapped_column(Text, default="", index=True)
    function: Mapped[str] = mapped_column(String(128), default="", index=True)
    seniority_band: Mapped[str] = mapped_column(String(64), default="", index=True)
    in_scope: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    match_evidence: Mapped[str] = mapped_column(Text, default="")
    first_seen_week: Mapped[str] = mapped_column(String(16), default="", index=True)
    last_seen_week: Mapped[str] = mapped_column(String(16), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open")  # open|removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    company: Mapped[Company] = relationship(back_populates="job_postings")


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"), index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), index=True)
    raw_payload_ref: Mapped[str] = mapped_column(Text, default="")


class JobDelta(Base):
    __tablename__ = "job_deltas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"), index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), index=True)
    change_type: Mapped[str] = mapped_column(String(32), default="")  # new|updated|removed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeeklyInsight(Base):
    __tablename__ = "weekly_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_id: Mapped[str] = mapped_column(String(16), index=True, default="")
    scrape_run_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_runs.id"), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    groq_model: Mapped[str] = mapped_column(String(128), default="")
    groq_prompt_version: Mapped[str] = mapped_column(String(64), default="")
    llm_status: Mapped[str] = mapped_column(String(32), default="")
    llm_brief: Mapped[str] = mapped_column(Text, default="")
    llm_priorities_json: Mapped[str] = mapped_column(Text, default="[]")
    llm_raw_response_ref: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, future=True, connect_args=connect_args)


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True), engine


def init_db(database_url: str) -> None:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
