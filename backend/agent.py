"""doit-voc-agent VOC 파이프라인 — pydantic-ai 기반 순차 처리 (스펙 §4.1).

classify → (route) → retrieve → generate_answer → compose_response → save → 반환
                └────→ escalate ──↗

그래프 라이브러리 없이 일반 Python 제어흐름으로 구성한다 — 분기가 하나뿐이라
StateGraph보다 단순하고, Langfuse 연동은 pydantic-ai의 OTel 계측으로 처리된다.
"""
import functools
from typing import Any, Callable, Dict, List, Optional

from pydantic_ai.models import Model

from backend.agents import AgentBundle, build_agents
from backend.manual_retrieval import ManualChunk, load_manual
from backend.nodes.answer import answer_step
from backend.nodes.classify import classify_step
from backend.nodes.escalate import escalate_step
from backend.nodes.respond import respond_step
from backend.nodes.retrieve import retrieve_step
from backend.nodes.save import save_state
from backend.state import AgentState


def route_after_classify(state: Dict[str, Any]) -> str:
    """분류 결과에 따른 경로 결정 (스펙 §4.2)."""
    category = state.get("category")
    priority = state.get("priority")
    if category in ("사용법문의", "칭찬"):
        return "retrieve"
    if category == "불만" and priority == "low":
        return "retrieve"
    return "escalate"


@functools.lru_cache(maxsize=1)
def _cached_manual() -> List[ManualChunk]:
    # 스펙 §5.3: 메뉴얼은 캐시하여 요청마다 재로드하지 않는다
    return load_manual()


def run_agent(
    voc_text: str,
    session_id: str,
    model: Optional[Model] = None,
    session_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """VOC 하나를 파이프라인으로 처리하고 최종 state를 반환."""
    agents: Optional[AgentBundle] = build_agents(model) if model is not None else None
    state: AgentState = {"voc_text": voc_text, "session_id": session_id}

    state.update(classify_step(state, agents))
    if route_after_classify(state) == "retrieve":
        state.update(retrieve_step(state, _cached_manual()))
        state.update(answer_step(state, agents))
    else:
        state.update(escalate_step(state, agents))
    state.update(respond_step(state))
    state.update(save_state(state, session_factory))
    return dict(state)
