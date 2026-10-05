"""VOC 분류 단계 — pydantic-ai 구조화 출력으로 유형 6종 + 우선순위 판정 (스펙 §4.2).

구조화 출력 검증 실패/LLM 실패 시 기타/medium 폴백 — 사용자는 에러를 보지 않는다 (스펙 §4.5).
"""
from typing import Any, Dict, Optional

from backend.agents import AgentBundle, classification_to_dict

FALLBACK_CLASSIFICATION = {"category": "기타", "priority": "medium"}


def classify_step(state: Dict[str, Any], agents: Optional[AgentBundle]) -> Dict[str, Any]:
    """voc_text를 분류해 state에 category/priority를 채운다."""
    voc_text = state["voc_text"]
    if agents is None:
        return {**FALLBACK_CLASSIFICATION, "error": "LLM 모델 미설정 — 폴백 분류 사용"}
    try:
        result = agents.classify.run_sync(
            voc_text, model_settings={"temperature": 0.0}
        ).output
    except Exception as exc:  # 우아한 열화 — 분류 실패가 전체를 죽이지 않게
        print(f"[classify] LLM 호출 실패, 폴백 분류 사용: {exc}")
        return {**FALLBACK_CLASSIFICATION, "error": f"classify 실패: {exc}"}
    return classification_to_dict(result)
