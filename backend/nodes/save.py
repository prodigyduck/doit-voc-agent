"""VOC 이력 저장 노드 — 저장 실패해도 응답을 막지 않는다 (스펙 §4.5)."""
from typing import Any, Callable, Dict

from backend.models import VocRecord


def make_save_node(session_factory: Callable):
    def save_node(state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            db = session_factory()
            try:
                record = VocRecord(
                    session_id=state.get("session_id") or "anonymous",
                    voc_text=state["voc_text"],
                    category=state.get("category", "기타"),
                    priority=state.get("priority", "medium"),
                    answer=state.get("answer"),
                    answer_sources=state.get("answer_sources") or [],
                    escalated=bool(state.get("escalated")),
                    # escalation_reason 컬럼이 String(200)이라 200자로 절단 —
                    # LLM 실패 사유가 길어 PostgreSQL INSERT가 실패하면 이력이 통째로 유실된다
                    escalation_reason=(state.get("escalation_reason") or "")[:200] or None,
                )
                db.add(record)
                db.commit()
                db.refresh(record)
                return {"voc_id": record.id}
            finally:
                db.close()
        except Exception as exc:
            print(f"[save] DB 저장 실패 (응답은 계속 반환): {exc}")
            return {"voc_id": None, "error": f"save 실패: {exc}"}

    return save_node
