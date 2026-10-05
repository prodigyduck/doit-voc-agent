"""최종 응답 조립 노드 (스펙 §4.1).

우선순위: answer(출처 포함) > escalation_message > 기본 안내.
answer에 출처가 없으면 안전장치로 덧붙인다.
"""
from typing import Any, Dict

from backend.nodes.escalate import DEFAULT_ESCALATION_MESSAGE


def make_respond_node():
    def respond_node(state: Dict[str, Any]) -> Dict[str, Any]:
        answer = state.get("answer")
        if answer:
            sources = state.get("answer_sources") or []
            if sources and not any(s in answer for s in sources):
                answer = answer + "\n\n📖 출처: " + ", ".join(sources)
            return {"response": answer}
        return {"response": state.get("escalation_message") or DEFAULT_ESCALATION_MESSAGE}

    return respond_node
