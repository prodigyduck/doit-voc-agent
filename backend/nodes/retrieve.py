"""메뉴얼 검색 노드 — manual_retrieval.search 래핑 (스펙 §4.1)."""
from typing import Any, Dict, List, Optional

from backend.manual_retrieval import ManualChunk, load_manual, search


def make_retrieve_node(chunks: Optional[List[ManualChunk]] = None):
    manual_chunks = chunks if chunks is not None else load_manual()

    def retrieve_node(state: Dict[str, Any]) -> Dict[str, Any]:
        results = search(
            manual_chunks,
            state["voc_text"],
            category=state.get("category"),
            top_k=3,
        )
        return {
            "manual_chunks": [
                {"file": c.file, "section": c.section, "content": c.content}
                for c in results
            ]
        }

    return retrieve_node
