"""메뉴얼 검색 단계 — manual_retrieval.search 래핑 (스펙 §4.1)."""
from typing import Any, Dict, List, Optional

from backend.manual_retrieval import ManualChunk, load_manual, search


def retrieve_step(
    state: Dict[str, Any], manual_chunks: Optional[List[ManualChunk]] = None
) -> Dict[str, Any]:
    chunks = manual_chunks if manual_chunks is not None else load_manual()
    results = search(
        chunks,
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
