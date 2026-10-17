from backend.models import VocRecord


def test_voc_record_생성_및_기본값(db_session):
    record = VocRecord(
        session_id="s1",
        voc_text="할 일이 저장되지 않아요",
        category="버그제보",
        priority="high",
    )
    db_session.add(record)
    db_session.commit()

    found = db_session.query(VocRecord).filter_by(session_id="s1").first()
    assert found is not None
    assert found.category == "버그제보"
    assert found.priority == "high"
    assert found.escalated is False          # 기본값
    assert found.escalation_status == "open"  # 기본값
    assert found.resolved_at is None
    assert found.created_at is not None


def test_상수_고정값():
    from backend.constants import CATEGORIES, PRIORITIES, ESCALATION_STATUSES
    assert CATEGORIES == ["사용법문의", "버그제보", "기능요청", "불만", "칭찬", "기타"]
    assert PRIORITIES == ["low", "medium", "high"]
    assert ESCALATION_STATUSES == ["open", "resolved"]


def test_설정_기본값_로드(monkeypatch):
    from backend.config import Settings, settings
    assert settings.database_url == "sqlite://"  # conftest가 덮어쓴 값

    # LLM 기본값은 로컬 .env(예: 라이브 E2E용 키)와 무관하게 검증
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    fresh = Settings()
    assert fresh.llm_provider == "openai_compat"
    assert fresh.llm_base_url == "https://api.openai.com/v1"
    assert fresh.llm_model == "gpt-4o-mini"


def test_judge_컬럼_기본값은_미채점(db_session):
    db_session.add(VocRecord(session_id="j1", voc_text="완료한 티켓이 사라졌어요", category="사용법문의", priority="low"))
    db_session.commit()

    found = db_session.query(VocRecord).filter_by(session_id="j1").first()
    assert found.judge_scores is None
    assert found.judge_total is None
    assert found.judge_cause is None
    assert found.judge_reason is None
    assert found.judged_at is None


def test_judge_설정_기본값(monkeypatch):
    from backend.config import Settings

    for key in ("JUDGE_ENABLED", "JUDGE_MODEL"):
        monkeypatch.delenv(key, raising=False)
    fresh = Settings()
    assert fresh.judge_enabled is True
    assert fresh.judge_model == ""


def test_엔진_팩토리_파일_sqlite는_커넥션_풀():
    """파일 SQLite가 StaticPool 단일 커넥션을 쓰면 동시 요청에서 sqlite3 C 레벨
    크래시(SIGSEGV)가 발생한다 — 파일은 커넥션 풀, 인메모리만 StaticPool."""
    from sqlalchemy.pool import StaticPool

    from backend.database import _create_engine

    file_engine = _create_engine("sqlite:///./doit_voc_agent.db")
    assert not isinstance(file_engine.pool, StaticPool)

    memory_engine = _create_engine("sqlite://")
    assert isinstance(memory_engine.pool, StaticPool)


def test_gap_status_기본값은_null(db_session):
    db_session.add(VocRecord(session_id="g1", voc_text="CSV 내보내기 문의", category="사용법문의", priority="low"))
    db_session.commit()

    found = db_session.query(VocRecord).filter_by(session_id="g1").first()
    assert found.gap_status is None
