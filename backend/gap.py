"""Phase 3 — 재료부족 큐 정의·마킹 (스펙 2026-08-23 §4).

큐 정의의 단일 진실 공급원. 카드(stats)·필터(vocs)·리포트(gap_report)는
모두 이 모듈의 predicate로만 큐를 판정한다 — 정의 중복 금지.
'open'은 저장하지 않는 파생 상태다(재료부족 판정 && gap_status IS NULL).
"""
from typing import List

from backend.models import VocRecord

GAP_RESOLVED = "resolved"  # 메뉴얼·FAQ 반영 완료
GAP_ABSENT = "absent"      # 기능 없음 확인 종결
GAP_STATUSES = (GAP_RESOLVED, GAP_ABSENT)


def is_material_gap(record) -> bool:
    """재료부족 판정 — Phase 2 카드 정의 그대로 (judge 스펙 §3, 2026-08-23 문구 교정판).

    judge 판정 경로와 결정론적 경로(사용법문의+에스컬레이션+출처 비어 있음)는
    상호배타다 — judge 대상은 answer_sources가 비어 있지 않다.
    """
    return (
        record.judge_cause == "재료부족"
        or (record.category == "사용법문의" and record.escalated and not record.answer_sources)
    )


def is_gap_open(record) -> bool:
    """미처리 큐 — 재료부족 판정 && 마킹 없음."""
    return is_material_gap(record) and record.gap_status is None


def iter_gap_open(db) -> List[VocRecord]:
    """미처리 큐 목록 — 생성일 순 (리포트·집계용)."""
    rows = db.query(VocRecord).order_by(VocRecord.created_at.asc()).all()
    return [r for r in rows if is_gap_open(r)]


def mark_gap(session_factory, voc_id: int, status: str) -> None:
    """큐 건에 처리 결과 마킹. 화이트리스트 밖 status·없는 voc_id는 ValueError."""
    if status not in GAP_STATUSES:
        raise ValueError(f"status는 {GAP_STATUSES} 중 하나여야 합니다: {status!r}")
    db = session_factory()
    try:
        record = db.query(VocRecord).filter(VocRecord.id == voc_id).first()
        if record is None:
            raise ValueError(f"voc_id={voc_id} 레코드가 없습니다")
        record.gap_status = status
        db.commit()
    finally:
        db.close()


def format_gap_report(records: List[VocRecord]) -> str:
    """미처리 큐 마크다운 리포트 — gap_report.py가 출력, 순수 함수라 테스트 대상."""
    if not records:
        return "미처리 큐 없음"
    lines = [f"## 재료부족 미처리 큐 — {len(records)}건"]
    for r in records:
        path = "judge" if r.judge_cause == "재료부족" else "결정론적"
        lines.append(f"### voc_id={r.id} [{path}] {r.created_at:%Y-%m-%d} {r.category}")
        lines.append(f"- 질문: {r.voc_text}")
        lines.append(f"- 답변(200자): {(r.answer or '')[:200]}")
        if r.judge_reason:
            lines.append(f"- 판정 근거: {r.judge_reason}")
        lines.append("")
    return "\n".join(lines).rstrip()
