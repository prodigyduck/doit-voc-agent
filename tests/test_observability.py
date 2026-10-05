"""observability 모듈 테스트 — Langfuse 활성 조건·OTel 스팬·score 업로드."""
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend import observability
from backend.config import Settings
from backend.judge import run_judge
from backend.models import VocRecord
from backend.observability import (
    pipeline_span,
    score_judge,
    trace_id_of,
    tracing_enabled,
)
from tests.fakes import FakeModel

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


def test_pipeline_span_비활성이면_none():
    with pipeline_span(_settings(enabled=False), "s1") as span:
        assert span is None
        assert trace_id_of(span) is None


def _sdk_tracer_with_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_pipeline_span_활성이면_스팬과_trace_id(monkeypatch):
    tracer, exporter = _sdk_tracer_with_exporter()
    monkeypatch.setattr(observability, "_get_tracer", lambda: tracer)

    with pipeline_span(_settings(), "sess-9") as span:
        assert span is not None
        trace_id = trace_id_of(span)

    assert trace_id is not None
    assert len(trace_id) == 32  # langfuse trace id 형식
    spans = exporter.get_finished_spans()
    assert spans[0].name == "voc_pipeline"
    assert spans[0].attributes["langfuse.session_id"] == "sess-9"


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

    run_judge(record.id, FakeModel([VALID_JUDGE]).model, db_session_factory, trace_id="t-j1")

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

    run_judge(record.id, FakeModel([VALID_JUDGE]).model, db_session_factory)

    assert fake.scores == []
