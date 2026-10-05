"""Langfuse 관측 — pydantic-ai OTel 스팬 + 채점 score 업로드.

활성 조건(LANGFUSE_ENABLED=true + 키 2개)을 만족할 때만 동작하고,
나머지 경우는 스팬/클라이언트를 만들지 않아 행동 변화가 없다.
모든 함수는 실패해도 예외를 밖으로 던지지 않는다(콘솔 로그만).

파이프라인 스팬은 OTel 글로벌 트레이서로 시작하고, agents.py의
instrument=True 에이전트 호출이 그 아래에 스팬으로 중첩된다.
langfuse v3는 OTel 네이티브라 get_client() 초기화 시 글로벌
TraceProvider가 langfuse exporter로 연결된다.
"""
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


def tracing_enabled(settings) -> bool:
    """Langfuse 트레이싱 활성 조건: 플래그 true + 공개/비밀 키 모두 존재."""
    return (
        bool(settings.langfuse_enabled)
        and bool(settings.langfuse_public_key)
        and bool(settings.langfuse_secret_key)
    )


_TRACER: Any = None


def _get_tracer():
    """langfuse가 연 글로벌 OTel 트레이서 반환 (실패 시 None)."""
    global _TRACER
    if _TRACER is None:
        try:
            from langfuse import get_client

            get_client()  # langfuse OTel 세팅 활성화 (키 없으면 경고만)
            from opentelemetry import trace

            _TRACER = trace.get_tracer("doit-voc-agent")
        except Exception as exc:
            print(f"[langfuse] 트레이서 초기화 실패: {exc}")
            _TRACER = False
    return _TRACER or None


@contextmanager
def pipeline_span(settings, session_id: str) -> Iterator[Optional[Any]]:
    """VOC 처리 전체를 감싸는 루트 스팬. 비활성/실패 시 yield None."""
    tracer = _get_tracer() if tracing_enabled(settings) else None
    if tracer is None:
        yield None
        return
    try:
        with tracer.start_as_current_span("voc_pipeline") as span:
            span.set_attribute("langfuse.session_id", session_id)
            span.set_attribute("langfuse.trace_name", "voc_pipeline")
            span.set_attribute("langfuse.tags", "voc-agent")
            yield span
    except Exception as exc:  # 관측 실패가 파이프라인을 죽이지 않게
        print(f"[langfuse] 파이프라인 스팬 실패: {exc}")
        yield None


def trace_id_of(span) -> Optional[str]:
    """스팬에서 OTel trace id를 32자 hex로 꺼낸다 — langfuse score 연결용."""
    if span is None:
        return None
    try:
        trace_id = span.get_span_context().trace_id
        return format(trace_id, "032x") if trace_id else None
    except Exception:
        return None


def _langfuse_client():
    """Langfuse 클라이언트 (테스트 monkeypatch 지점)."""
    from langfuse import get_client

    return get_client()


def score_judge(trace_id: Optional[str], parsed: Dict[str, Any]) -> None:
    """채점 결과를 Langfuse 트레이스에 score로 올린다. 실패는 로그만 남긴다."""
    if not trace_id:
        return
    total = parsed["completeness"] + parsed["accuracy"] + parsed["fluency"]
    comment = (
        f"completeness={parsed['completeness']}/accuracy={parsed['accuracy']}"
        f"/fluency={parsed['fluency']} | {parsed['cause']}: {parsed.get('reason') or ''}"
    )
    try:
        client = _langfuse_client()
        client.create_score(
            trace_id=trace_id,
            name="judge_total",
            value=total,
            data_type="NUMERIC",
            comment=comment,
        )
        client.flush()
    except Exception as exc:  # 채점 score 업로드 실패가 서비스를 죽이지 않게
        print(f"[langfuse] score 업로드 실패: {exc}")
