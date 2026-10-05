"""에스컬레이션 노드 — 접수 안내 문구 생성 + 플래그 (스펙 §4.1).

LLM 문구 생성에 실패해도 정적 문구로 응답한다 (스펙 §4.5).
"""
from typing import Any, Dict, Optional

from backend.llm.base import LLMProvider

ESCALATION_MESSAGES = {
    "버그제보": "버그 제보를 알려주셔서 감사합니다. 담당자에게 전달했으며 확인 후 조치하겠습니다.",
    "기능요청": "소중한 기능 요청 감사합니다. 제품팀에 전달하여 검토하겠습니다.",
    "불만": "불편을 드려 죄송합니다. 담당자가 내용을 확인하여 빠르게 답변드리겠습니다.",
    "기타": "문의 내용을 담당자에게 전달했습니다. 확인 후 안내드리겠습니다.",
}
DEFAULT_ESCALATION_MESSAGE = "문의 내용을 담당자에게 전달했습니다. 확인 후 안내드리겠습니다."

ESCALATE_PROMPT = """당신은 칸반 보드 앱 'doit'의 고객 지원 담당자입니다.
아래 VOC는 사람이 확인해야 하는 {category} 유형입니다.
사용자에게 전달할 접수 완료 안내 문구를 2~3문장의 친절한 한국어로 작성하세요.
해결 방법이나 일정을 지어내지 말고, 접수되었음과 검토하겠다는 점만 안내하세요.

[VOC]
{voc_text}"""


def make_escalate_node(provider: Optional[LLMProvider]):
    def escalate_node(state: Dict[str, Any]) -> Dict[str, Any]:
        category = state.get("category", "기타")
        reason = state.get("escalation_reason") or f"{category} 유형은 사람 확인이 필요합니다"
        message = ESCALATION_MESSAGES.get(category, DEFAULT_ESCALATION_MESSAGE)
        if provider is not None:
            try:
                message = provider.generate(
                    ESCALATE_PROMPT.format(category=category, voc_text=state["voc_text"]),
                    temperature=0.3,
                )
            except Exception as exc:
                print(f"[escalate] LLM 호출 실패, 정적 문구 사용: {exc}")
        return {"escalated": True, "escalation_reason": reason, "escalation_message": message}

    return escalate_node
