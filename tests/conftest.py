import os

# 백엔드 임포트 전에 테스트 환경 변수 설정 — DB를 SQLite 인메모리로 강제
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["LLM_API_KEY"] = "test-key"
# Langfuse 트레이싱은 테스트에서 항상 비활성 (네트워크 없음 보장)
os.environ.pop("LANGFUSE_ENABLED", None)
os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
os.environ.pop("LANGFUSE_SECRET_KEY", None)

import pytest

from backend.database import Base, SessionLocal, engine


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def db_session_factory():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal
