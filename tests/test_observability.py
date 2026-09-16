"""observability 모듈 테스트 — Langfuse 활성 조건·핸들러·콜백 전달·score 업로드."""
from langchain_core.callbacks.base import BaseCallbackHandler
from langfuse.langchain import CallbackHandler

from backend import observability
from backend.agent import run_agent
from backend.config import Settings
from backend.judge import run_judge
from backend.models import VocRecord
from backend.observability import (
    get_trace_id,
    make_trace_handler,
    score_judge,
    tracing_enabled,
)
from tests.fakes import FakeProvider

CLASSIFY_HOWTO = '{"category": "사용법문의", "priority": "low"}'
ANSWER = (
    "완료한 티켓은 24시간이 지나면 Done 칼럼에서 숨겨집니다. "
    "캘린더 연동 설정에서 다시 확인할 수 있어요.\n"
    "📖 출처: 04-troubleshooting#완료한 티켓이 보드에서 사라졌어요"
)
VALID_JUDGE = (
    '{"completeness": 4, "accuracy": 5, "fluency": 5,'
    ' "cause": "재료부족", "reason": "복구 절차가 출처에 없음"}'
)


def _settings(enabled=True, public="pk-test", secret="sk-test") -> Settings:
    settings = Settings()
    settings.langfuse_enabled = enabled
    settings.langfuse_public_key = public
    settings.langfuse_secret_key = secret
    return settings


def test_tracing_enabled_플래그와_키_둘다_필요():
    assert tracing_enabled(_settings(enabled=False)) is False
    assert tracing_enabled(_settings(enabled=True, public="")) is False
    assert tracing_enabled(_settings(enabled=True, secret="")) is False
    assert tracing_enabled(_settings()) is True


def test_make_trace_handler_비활성이면_none():
    assert make_trace_handler(_settings(enabled=False), "s1") is None
    assert make_trace_handler(_settings(enabled=True, public="", secret=""), "s1") is None


def test_make_trace_handler_활성이면_세션_핸들러():
    handler = make_trace_handler(_settings(), "sess-1")
    assert isinstance(handler, CallbackHandler)


def test_get_trace_id_none_안전():
    assert get_trace_id(None) is None


class Recorder(BaseCallbackHandler):
    def __init__(self):
        super().__init__()
        self.chain_starts = []

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        self.chain_starts.append(run_id)


def test_run_agent_콜백으로_노드_실행_기록(db_session_factory):
    recorder = Recorder()
    provider = FakeProvider([CLASSIFY_HOWTO, ANSWER])
    run_agent(
        "완료한 티켓이 사라졌어요",
        "s-cb",
        provider=provider,
        session_factory=db_session_factory,
        callbacks=[recorder],
    )
    assert len(recorder.chain_starts) >= 1


def test_run_agent_콜백_기본값_경로_불변(db_session_factory):
    provider = FakeProvider([CLASSIFY_HOWTO, ANSWER])
    result = run_agent(
        "완료한 티켓이 사라졌어요",
        "s-nc",
        provider=provider,
        session_factory=db_session_factory,
    )
    assert result["voc_id"] is not None


class FakeLangfuse:
    def __init__(self):
        self.scores = []
        self.flush_count = 0

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def flush(self):
        self.flush_count += 1


def test_score_judge_합계와_코멘트_업로드(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_langfuse_client", lambda: fake)
    parsed = {
        "completeness": 4,
        "accuracy": 5,
        "fluency": 5,
        "cause": "재료부족",
        "reason": "복구 절차 없음",
    }
    score_judge("trace-1", parsed)
    assert fake.scores[0]["trace_id"] == "trace-1"
    assert fake.scores[0]["name"] == "judge_total"
    assert fake.scores[0]["value"] == 14
    assert "재료부족" in fake.scores[0]["comment"]
    assert fake.flush_count == 1


def test_score_judge_trace_id_없으면_미호출(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_langfuse_client", lambda: fake)
    score_judge(None, {"completeness": 5, "accuracy": 5, "fluency": 5, "cause": "해당없음", "reason": None})
    assert fake.scores == []


def _add_record(db, **kw) -> VocRecord:
    defaults = dict(
        session_id="o",
        voc_text="티켓을 어떻게 삭제하나요?",
        category="사용법문의",
        priority="low",
        answer="삭제 버튼으로 지울 수 있습니다.",
        answer_sources=["02-managing-todos#티켓 삭제하기"],
    )
    defaults.update(kw)
    record = VocRecord(**defaults)
    db.add(record)
    db.commit()
    return record


def test_run_judge_trace_id_있으면_score_업로드(db_session_factory, monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_langfuse_client", lambda: fake)
    db = db_session_factory()
    record = _add_record(db)

    run_judge(record.id, FakeProvider([VALID_JUDGE]), db_session_factory, trace_id="t-j1")

    assert fake.scores and fake.scores[0]["trace_id"] == "t-j1"
    db2 = db_session_factory()
    found = db2.query(VocRecord).filter(VocRecord.id == record.id).first()
    db2.close()
    assert found.judge_total == 14


def test_run_judge_trace_id_없으면_score_미업로드(db_session_factory, monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_langfuse_client", lambda: fake)
    db = db_session_factory()
    record = _add_record(db)

    run_judge(record.id, FakeProvider([VALID_JUDGE]), db_session_factory)

    assert fake.scores == []
