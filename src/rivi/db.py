from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from rivi.config import Settings, get_settings, project_root
from rivi.models import init_db, make_session_factory


def resolve_database_url(settings: Settings | None = None) -> str:
    """Make sqlite paths absolute so the DB is always under the project data dir."""
    settings = settings or get_settings()
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        rel = url.removeprefix("sqlite:///./")
        abs_path = (project_root() / rel).resolve()
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{abs_path}"
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        path_part = url.removeprefix("sqlite:///")
        if not path_part.startswith("/"):
            abs_path = (project_root() / path_part).resolve()
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{abs_path}"
    return url


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or get_settings()
    url = resolve_database_url(settings)
    init_db(url)
    factory, _ = make_session_factory(url)
    return factory


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
