from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.services.analysis_dispatch import AnalysisDispatcher, get_analysis_dispatcher
from app.services.analysis_pipeline import AnalysisProcessor, get_analysis_processor


@pytest.fixture
def session_factory(tmp_path) -> Generator[sessionmaker[Session], None, None]:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_analysis_processor] = (
        lambda: AnalysisProcessor(session_factory=session_factory, enable_remote_calls=False)
    )
    app.dependency_overrides[get_analysis_dispatcher] = lambda: AnalysisDispatcher(run_inline=True)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
