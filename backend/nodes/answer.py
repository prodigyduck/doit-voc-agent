"""메뉴얼 근거 답변 노드 — 환각 방지 핵심 (스펙 §4.5, §5.4).

근거(청크)가 없으면 LLM을 호출하지 않고 정직하게 안내한 뒤 에스컬레이션한다.
"""
from typing import Any, Dict, List, Optional

from backend.llm.base import LLMProvider

NO_MANUAL_ANSWER = (
    "죄송합니다. 현재 doit 메뉴얼에서 이 문의에 대한 내용을 찾지 못했습니다.\n"
    "담당자에게 전달하여 확인 후 안내드리겠습니다."
)

FALLBACK_ANSWER = "죄송합니다. 지금은 답변을 생성하지 못했습니다. 담당자에게 전달하겠습니다."

ANSWER_PROMPT = """당신은 칸반 보드 앱 'doit'의 고객 지원 담당자입니다.

아래 [메뉴얼 근거]에 있는 내용만 사용해서 사용자 VOC에 답변하세요.
- 근거에 없는 내용을 절대 지어내지 마세요.
- 근거가 일부만 있으면 있는 내용만 안내하세요.
- 친절하고 간결한 한국어로 작성하고, 절차가 있으면 번호 목록을 사용하세요.

[사용자 VOC]
{voc_text}

[메뉴얼 근거]
{chunks_text}

답변 마지막 줄에 아래 형식으로 출처를 모두 나열하세요.
📖 출처: 파일명#섹션제목"""


def build_answer_prompt(voc_text: str, chunks: List[dict]) -> str:
    chunks_text = "\n\n".join(
        f"### {c['section']} ({c['file']})\n{c['content']}" for c in chunks
    )
    return ANSWER_PROMPT.format(voc_text=voc_text, chunks_text=chunks_text)


def _sources_of(chunks: List[dict]) -> List[str]:
    return [f"{c['file']}#{c['section']}" for c in chunks]


def make_answer_node(provider: Optional[LLMProvider]):
    def answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
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

        if provider is None:
            return {
                "answer": FALLBACK_ANSWER,
                "answer_sources": _sources_of(chunks),
                "escalated": True,
                "escalation_reason": "LLM provider 미설정",
            }

        try:
            answer = provider.generate(
                build_answer_prompt(voc_text, chunks), temperature=0.2
            )
        except Exception as exc:
            print(f"[answer] LLM 호출 실패, 폴백 응답 사용: {exc}")
            return {
                "answer": FALLBACK_ANSWER,
                "answer_sources": _sources_of(chunks),
                "escalated": True,
                "escalation_reason": f"답변 생성 실패: {exc}",
            }

        return {
            "answer": answer,
            "answer_sources": _sources_of(chunks),
            "escalated": False,
        }

    return answer_node
