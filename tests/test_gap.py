"""gap 모듈 테스트 (스펙 2026-08-23 §4·§9)."""
import pytest

from backend.gap import (
    GAP_STATUSES,
    format_gap_report,
    is_gap_open,
    is_material_gap,
    iter_gap_open,
    mark_gap,
)
from backend.models import VocRecord


class _R:
    """predicate 테스트용 가짜 레코드 — DB 없이 필드만 셋업."""

    def __init__(self, judge_cause=None, category="사용법문의", escalated=False,
                 answer_sources=None, gap_status=None):
        self.judge_cause = judge_cause
        self.category = category
        self.escalated = escalated
        self.answer_sources = answer_sources
        self.gap_status = gap_status


def test_is_material_gap_judge_판정():
    assert is_material_gap(_R(judge_cause="재료부족")) is True
    assert is_material_gap(_R(judge_cause="과정오류")) is False
    assert is_material_gap(_R(judge_cause="해당없음")) is False


def test_is_material_gap_결정론적_행렬():
    assert is_material_gap(_R(escalated=True, answer_sources=None)) is True         # 무출처
    assert is_material_gap(_R(escalated=True, answer_sources=[])) is True           # 빈 배열도 비어 있음
    assert is_material_gap(_R(escalated=True, answer_sources=["02#a"])) is False    # 출처 있음
    assert is_material_gap(_R(escalated=False, answer_sources=None)) is False       # 에스컬레이션 아님
    assert is_material_gap(_R(category="버그제보", escalated=True, answer_sources=None)) is False


def test_is_gap_open_마킹에_따라_거짓():
    assert is_gap_open(_R(judge_cause="재료부족")) is True
    assert is_gap_open(_R(judge_cause="재료부족", gap_status="resolved")) is False
    assert is_gap_open(_R(judge_cause="재료부족", gap_status="absent")) is False
    assert is_gap_open(_R(judge_cause="과정오류")) is False


def _add(db, **kw):
    defaults = dict(
        session_id="g", voc_text="CSV 내보내기 문의", category="사용법문의", priority="low",
        answer="찾지 못했습니다", answer_sources=None, escalated=True,
    )
    defaults.update(kw)
    record = VocRecord(**defaults)
    db.add(record)
    db.commit()
    return record


def test_mark_gap_마킹_저장(db_session_factory):
    db = db_session_factory()
    record = _add(db)
    voc_id = record.id  # detach 전에 캡처 — 세션을 닫아도 mark_gap가 자체 세션으로 동작함을 증명
    db.close()

    mark_gap(db_session_factory, voc_id, "resolved")

    db = db_session_factory()
    found = db.query(VocRecord).filter(VocRecord.id == voc_id).first()
    db.close()
    assert found.gap_status == "resolved"


def test_mark_gap_화이트리스트_밖은_ValueError(db_session_factory):
    with pytest.raises(ValueError):
        mark_gap(db_session_factory, 1, "완료")


def test_mark_gap_없는_voc_id는_ValueError(db_session_factory):
    with pytest.raises(ValueError):
        mark_gap(db_session_factory, 9999, GAP_STATUSES[0])


def test_iter_gap_open_미처리만(db_session_factory):
    from backend.database import SessionLocal  # noqa: F401 — fixture가 엔진 초기화
    db = db_session_factory()
    _add(db)  # 결정론적 미처리
    _add(db, session_id="g2", judge_cause="재료부족", judge_total=8,
         answer="부정 안내", answer_sources=["02#a"], escalated=False)  # judge 경로 미처리
    _add(db, session_id="g3", judge_cause="재료부족", judge_total=9, gap_status="absent",
         answer="부정 안내", answer_sources=["02#a"], escalated=False)  # 마킹됨
    _add(db, session_id="g4", category="버그제보", answer="접수했습니다.", escalated=True)  # 대상 아님
    open_records = iter_gap_open(db)
    db.close()
    assert len(open_records) == 2


def test_format_gap_report_필드_포함(db_session_factory):
    from backend.database import SessionLocal  # noqa: F401
    db = db_session_factory()
    record = _add(db, judge_cause="재료부족", judge_total=8, judge_reason="출처에 해결책 없음",
                  answer="부정 안내", answer_sources=["02#a"], escalated=False)
    report = format_gap_report(iter_gap_open(db))
    db.close()
    assert "재료부족 미처리 큐 — 1건" in report
    assert f"voc_id={record.id} [judge]" in report
    assert "CSV 내보내기 문의" in report
    assert "판정 근거: 출처에 해결책 없음" in report


def test_format_gap_report_결정론적_경로_표시(db_session_factory):
    from backend.database import SessionLocal  # noqa: F401
    db = db_session_factory()
    _add(db)  # judge_cause=None — 결정론적 경로
    report = format_gap_report(iter_gap_open(db))
    db.close()
    assert "[결정론적]" in report


def test_format_gap_report_0건():
    assert format_gap_report([]) == "미처리 큐 없음"
