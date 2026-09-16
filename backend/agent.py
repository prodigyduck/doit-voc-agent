"""doit-voc-agent LangGraph 그래프 — VOC 조건부 파이프라인 (스펙 §4.1).

classify → (route) → retrieve → generate_answer → compose_response → save → END
                └────→ escalate ──↗
"""
import functools
from typing import Any, Callable, Dict, List, Optional

from langgraph.graph import END, START, StateGraph

from backend.llm.base import LLMProvider
from backend.manual_retrieval import ManualChunk, load_manual
from backend.nodes.answer import make_answer_node
from backend.nodes.classify import make_classify_node
from backend.nodes.escalate import make_escalate_node
from backend.nodes.respond import make_respond_node
from backend.nodes.retrieve import make_retrieve_node
from backend.nodes.save import make_save_node
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


def build_graph(
    provider: Optional[LLMProvider],
    manual_chunks: Optional[List[ManualChunk]] = None,
    session_factory: Optional[Callable] = None,
):
    chunks = manual_chunks if manual_chunks is not None else load_manual()
    builder = StateGraph(AgentState)

    builder.add_node("classify", make_classify_node(provider))
    builder.add_node("retrieve", make_retrieve_node(chunks))
    builder.add_node("generate_answer", make_answer_node(provider))
    builder.add_node("escalate", make_escalate_node(provider))
    builder.add_node("compose_response", make_respond_node())
    builder.add_node("save", make_save_node(session_factory))

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {"retrieve": "retrieve", "escalate": "escalate"},
    )
    builder.add_edge("retrieve", "generate_answer")
    builder.add_edge("generate_answer", "compose_response")
    builder.add_edge("escalate", "compose_response")
    builder.add_edge("compose_response", "save")
    builder.add_edge("save", END)

    return builder.compile()


@functools.lru_cache(maxsize=4)
def _compiled_graph(provider, session_factory):
    # 스펙 §5.3: 그래프와 메뉴얼은 캐시하여 요청마다 재컴파일/재로드하지 않는다
    return build_graph(provider, manual_chunks=None, session_factory=session_factory)


def run_agent(
    voc_text: str,
    session_id: str,
    provider: Optional[LLMProvider] = None,
    session_factory: Optional[Callable] = None,
    callbacks: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """VOC 하나를 그래프로 처리하고 최종 state를 반환.

    callbacks는 Langfuse 등 관측 핸들러용 — 그래프 노드 실행이 기록된다.
    """
    graph = _compiled_graph(provider, session_factory)
    initial_state: AgentState = {"voc_text": voc_text, "session_id": session_id}
    return graph.invoke(
        initial_state,
        config={"callbacks": callbacks} if callbacks else None,
    )
