"""Langfuse 관측 — 그래프 트레이싱·채점 score 업로드 (스펙: 관측 연동).

활성 조건(LANGFUSE_ENABLED=true + 키 2개)을 만족할 때만 동작하고,
나머지 경우는 핸들러/클라이언트를 만들지 않아 행동 변화가 없다.
모든 함수는 실패해도 예외를 밖으로 던지지 않는다(콘솔 로그만).
"""
from typing import Any, Dict, Optional

from langfuse import get_client
from langfuse.langchain import CallbackHandler

TRACE_NAME = "voc_pipeline"
TRACE_TAGS = ["voc-agent"]


def tracing_enabled(settings) -> bool:
    """Langfuse 트레이싱 활성 조건: 플래그 true + 공개/비밀 키 모두 존재."""
    return (
        bool(settings.langfuse_enabled)
        and bool(settings.langfuse_public_key)
        and bool(settings.langfuse_secret_key)
    )


class VocTraceHandler(CallbackHandler):
    """voc_pipeline 트레이스에 세션 메타데이터를 붙이는 핸들러.

    루트 체인 시작 시점(트레이스 컨텍스트가 살아 있을 때)에만 한 번
    update_current_trace로 이름·세션·태그를 설정한다.
    """

    def __init__(self, session_id: str):
        super().__init__()
        self._voc_session_id = session_id
        self._trace_tagged = False

    def on_chain_start(
        self,
        serialized,
        inputs,
        *,
        run_id,
        parent_run_id=None,
        tags=None,
        metadata=None,
        **kwargs,
    ):
        super().on_chain_start(
            serialized,
            inputs,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **kwargs,
        )
        if parent_run_id is None and not self._trace_tagged:
            self._trace_tagged = True
            try:
                get_client().update_current_trace(
                    name=TRACE_NAME,
                    session_id=self._voc_session_id,
                    tags=list(TRACE_TAGS),
                )
            except Exception as exc:  # 관측 실패가 파이프라인을 죽이지 않게
                print(f"[langfuse] 트레이스 메타데이터 설정 실패: {exc}")


def make_trace_handler(settings, session_id: str) -> Optional[Any]:
    """활성 상태면 세션 트레이스 핸들러를 반환, 아니면 None."""
    if not tracing_enabled(settings):
        return None
    try:
        return VocTraceHandler(session_id)
    except Exception as exc:
        print(f"[langfuse] 트레이스 핸들러 생성 실패: {exc}")
        return None


def get_trace_id(handler) -> Optional[str]:
    """핸들러에서 마지막 트레이스 id를 안전하게 꺼낸다."""
    if handler is None:
        return None
    try:
        return handler.last_trace_id
    except Exception:
        return None


def _langfuse_client():
    """Langfuse 클라이언트 (테스트 monkeypatch 지점)."""
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
