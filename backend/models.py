"""VOC 이력 ORM 모델 (스펙 §4.4)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from backend.database import Base


class VocRecord(Base):
    __tablename__ = "voc_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True, nullable=False)
    voc_text = Column(Text, nullable=False)
    category = Column(String(20), nullable=False, default="기타")
    priority = Column(String(10), nullable=False, default="medium")
    answer = Column(Text, nullable=True)
    answer_sources = Column(JSON, nullable=True)  # List[str] — 에스컬레이션 경로는 null
    escalated = Column(Boolean, nullable=False, default=False)
    escalation_reason = Column(String(200), nullable=True)
    escalation_status = Column(String(10), nullable=False, default="open")
    # Phase 2 — LLM-as-a-Judge 채점 결과 (스펙 2026-08-21 §3). 미채점은 전부 null
    judge_scores = Column(JSON, nullable=True)       # {"completeness": 1-5, "accuracy": 1-5, "fluency": 1-5}
    judge_total = Column(Integer, nullable=True)     # 세 축 합계 3~15
    judge_cause = Column(String(20), nullable=True)  # "재료부족"|"과정오류"|"해당없음"
    judge_reason = Column(String(200), nullable=True)
    judged_at = Column(DateTime, nullable=True)
    # Phase 3 — 재료부족 큐 처리 상태 (스펙 2026-08-23 §3).
    # null=미처리, 'resolved'=메뉴얼·FAQ 반영, 'absent'=기능 없음 확인 종결. 'open'은 파생 상태라 저장 안 함
    gap_status = Column(String(12), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
