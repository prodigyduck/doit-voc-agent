"""Phase 2 — LLM-as-a-Judge 채점 (스펙 2026-08-21).

답변 생성 경로(answer_sources가 있는 건)만 채점한다. LLM 실패·파싱 실패는
미채점(null)로 남긴다 — 채점은 응답 후 백그라운드라 사용자 영향이 없다.
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic_ai.models import Model

from backend.agents import build_agents
from backend.config import Settings
from backend.manual_retrieval import load_manual
from backend.models import VocRecord
from backend.observability import score_judge


def get_judge_model(settings: Settings, fallback_model):
    """JUDGE_MODEL이 설정되면 채점 전용 모델을 생성, 아니면 fallback 재사용."""
    if settings.judge_model and settings.judge_model != settings.llm_model:
        from backend.llm import get_model

        return get_model(settings, model=settings.judge_model) or fallback_model
    return fallback_model


JUDGE_CAUSES = ("재료부족", "과정오류", "해당없음")
AXES = ("completeness", "accuracy", "fluency")

JUDGE_OUTPUT_FORMAT = """아래 JSON 형식만 출력하세요. 다른 설명은 금지합니다.
{"completeness": 4, "accuracy": 5, "fluency": 5, "cause": "재료부족|과정오류|해당없음", "reason": "감점 근거 한 줄"}"""


def parse_judge(text: str) -> Optional[Dict[str, Any]]:
    """LLM 출력에서 채점 JSON 추출·검증. 실패 시 None(미채점)."""
    match = re.search(r"\{[^{}]*\}", text or "", re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data.get("cause") in JUDGE_CAUSES:
            scores: Dict[str, int] = {}
            for axis in AXES:
                value = data.get(axis)
                if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                    return None
                scores[axis] = value
            raw_reason = data.get("reason")
            reason = str(raw_reason).strip()[:200] if raw_reason else None
            return {**scores, "cause": data["cause"], "reason": reason}
    return None


def should_judge(record) -> bool:
    """채점 대상: 답변 생성 경로(answer_sources가 있는 건)만. (스펙 §3)"""
    return bool(record.answer_sources) and bool(record.answer)


def _source_contents(sources: List[str]) -> str:
    chunks = {c.source: c.content for c in load_manual()}
    parts = []
    for source in sources:
        parts.append(f"--- {source} ---\n{chunks.get(source, '(출처를 찾을 수 없음)')}")
    return "\n\n".join(parts)


def build_judge_message(record) -> str:
    return (
        f"[원본 VOC]\n{record.voc_text}\n\n"
        f"[생성된 답변]\n{record.answer or ''}\n\n"
        f"[참조한 메뉴얼 출처]\n{_source_contents(record.answer_sources or [])}\n\n"
        f"{JUDGE_OUTPUT_FORMAT}"
    )


def run_judge(voc_id: int, model: Optional[Model], session_factory, trace_id: Optional[str] = None) -> None:
    """레코드 1건을 채점해 업데이트. 어떤 실패도 조용히 로그로만 남긴다.

    trace_id가 있으면 Langfuse에 채점 score를 올린다(관측 비활성 시 무시).
    """
    db = session_factory()
    try:
        record = db.query(VocRecord).filter(VocRecord.id == voc_id).first()
        if record is None or model is None or not should_judge(record):
            return
        raw = build_agents(model).judge.run_sync(
            build_judge_message(record), model_settings={"temperature": 0.0}
        ).output
        parsed = parse_judge(raw)
        if parsed is None:
            print(f"[judge] 채점 파싱 실패 voc_id={voc_id} — 미채점 유지")
            return
        record.judge_scores = {axis: parsed[axis] for axis in AXES}
        record.judge_total = sum(parsed[axis] for axis in AXES)
        record.judge_cause = parsed["cause"]
        record.judge_reason = parsed["reason"]
        record.judged_at = datetime.utcnow()
        db.commit()
        score_judge(trace_id, parsed)  # 내부에서 실패를 삼키므로 DB 커밋 영향 없음
    except Exception as exc:  # 채점 실패가 서비스를 죽이지 않게 (스펙 §4 폴백)
        print(f"[judge] 채점 실패 voc_id={voc_id}: {exc}")
    finally:
        db.close()


def iter_judge_pending(db) -> List[VocRecord]:
    """미채점 && 채점 대상 건 반환 (백필 스크립트용)."""
    return [
        r for r in db.query(VocRecord).all()
        if r.judge_scores is None and should_judge(r)
    ]
