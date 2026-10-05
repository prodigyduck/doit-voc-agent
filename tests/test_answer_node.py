"""answer/retrieve 단계 테스트 — 환각 방지 핵심 검증."""
from backend.agents import ANSWER_INSTRUCTIONS, build_agents
from backend.nodes.answer import (
    FALLBACK_ANSWER,
    NO_MANUAL_ANSWER,
    answer_step,
    build_answer_message,
)
from backend.nodes.retrieve import retrieve_step
from tests.fakes import FakeModel

CHUNKS = [
    {
        "file": "03-ui-guide",
        "section": "할 일 삭제하기",
        "content": "## 할 일 삭제하기\n항목에 마우스를 올려 삭제 버튼을 누릅니다.",
    }
]


def _agents(fake):
    return build_agents(fake.model)


def test_근거_있으면_답변_생성():
    fake = FakeModel(["삭제 버튼을 누르세요.\n📖 출처: 03-ui-guide#할 일 삭제하기"])
    result = answer_step(
        {"voc_text": "삭제 어떻게 해요?", "manual_chunks": CHUNKS}, _agents(fake)
    )
    assert result["escalated"] is False
    assert result["answer_sources"] == ["03-ui-guide#할 일 삭제하기"]
    assert "📖 출처" in result["answer"]


def test_근거_없으면_답변_금지_에스컬레이션():
    """환각 방지 핵심 테스트 (스펙 §4.5) — 근거 없으면 LLM을 호출조차 하지 않는다."""
    fake = FakeModel(["지어낸 답변"])
    result = answer_step(
        {"voc_text": "테마 색을 분홍색으로 바꾸고 싶어요", "manual_chunks": []},
        _agents(fake),
    )
    assert result["answer"] == NO_MANUAL_ANSWER
    assert result["escalated"] is True
    assert result["answer_sources"] == []
    assert fake.calls == []  # LLM 미호출 확인


def test_LLM_실패시_폴백_답변():
    fake = FakeModel([])  # 응답 없음 → 예외
    result = answer_step({"voc_text": "x", "manual_chunks": CHUNKS}, _agents(fake))
    assert result["answer"] == FALLBACK_ANSWER
    assert result["escalated"] is True


def test_agents_None이면_폴백_답변():
    result = answer_step({"voc_text": "x", "manual_chunks": CHUNKS}, None)
    assert result["answer"] == FALLBACK_ANSWER
    assert result["escalated"] is True


def test_메시지에_근거와_VOC_포함():
    message = build_answer_message("삭제 어떻게 해요?", CHUNKS)
    assert "삭제 어떻게 해요?" in message
    assert "할 일 삭제하기" in message
    assert "지어내" in ANSWER_INSTRUCTIONS  # 환각 금지 지시는 지시문에 상주


def test_retrieve_실제_메뉴얼_검색():
    result = retrieve_step({"voc_text": "할 일이 저장되지 않아요", "category": "사용법문의"})
    assert len(result["manual_chunks"]) >= 1
    first = result["manual_chunks"][0]
    assert set(first.keys()) == {"file", "section", "content"}
