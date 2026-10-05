"""메뉴얼 근거 답변 단계 — 환각 방지 핵심 (스펙 §4.5, §5.4).

근거(청크)가 없으면 LLM을 호출하지 않고 정직하게 안내한 뒤 에스컬레이션한다.
"""
from typing import Any, Dict, List, Optional

from backend.agents import AgentBundle

NO_MANUAL_ANSWER = (
    "죄송합니다. 현재 doit 메뉴얼에서 이 문의에 대한 내용을 찾지 못했습니다.\n"
    "담당자에게 전달하여 확인 후 안내드리겠습니다."
)

FALLBACK_ANSWER = "죄송합니다. 지금은 답변을 생성하지 못했습니다. 담당자에게 전달하겠습니다."


def build_answer_message(voc_text: str, chunks: List[dict]) -> str:
    chunks_text = "\n\n".join(
        f"### {c['section']} ({c['file']})\n{c['content']}" for c in chunks
    )
    return f"[사용자 VOC]\n{voc_text}\n\n[메뉴얼 근거]\n{chunks_text}"


def sources_of(chunks: List[dict]) -> List[str]:
    return [f"{c['file']}#{c['section']}" for c in chunks]


def answer_step(state: Dict[str, Any], agents: Optional[AgentBundle]) -> Dict[str, Any]:
    chunks = state.get("manual_chunks") or []
    voc_text = state["voc_text"]

    if not chunks:
        # 환각 방지 — 근거 없으면 답변 생성 금지 (스펙 §4.5)
        return {
            "answer": NO_MANUAL_ANSWER,
            "answer_sources": [],
            "escalated": True,
            "escalation_reason": "메뉴얼에 근거 없는 문의",
        }

    if agents is None:
        return {
            "answer": FALLBACK_ANSWER,
            "answer_sources": sources_of(chunks),
            "escalated": True,
            "escalation_reason": "LLM 모델 미설정",
        }

    try:
        answer = agents.answer.run_sync(
            build_answer_message(voc_text, chunks),
            model_settings={"temperature": 0.2},
        ).output
    except Exception as exc:
        print(f"[answer] LLM 호출 실패, 폴백 응답 사용: {exc}")
        return {
            "answer": FALLBACK_ANSWER,
            "answer_sources": sources_of(chunks),
            "escalated": True,
            "escalation_reason": f"답변 생성 실패: {exc}",
        }

    return {
        "answer": answer,
        "answer_sources": sources_of(chunks),
        "escalated": False,
    }
