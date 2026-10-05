"""answer node + retrieve node 테스트 — 환각 방지 핵심 검증."""
from backend.nodes.answer import (
    FALLBACK_ANSWER,
    NO_MANUAL_ANSWER,
    build_answer_prompt,
    make_answer_node,
)
from backend.nodes.retrieve import make_retrieve_node
from tests.fakes import FakeProvider

CHUNKS = [
    {
        "file": "03-ui-guide",
        "section": "할 일 삭제하기",
        "content": "## 할 일 삭제하기\n항목에 마우스를 올려 삭제 버튼을 누릅니다.",
    }
]


def test_근거_있으면_답변_생성():
    provider = FakeProvider(["삭제 버튼을 누르세요.\n📖 출처: 03-ui-guide#할 일 삭제하기"])
    node = make_answer_node(provider)
    result = node({"voc_text": "삭제 어떻게 해요?", "manual_chunks": CHUNKS})
    assert result["escalated"] is False
    assert result["answer_sources"] == ["03-ui-guide#할 일 삭제하기"]
    assert "📖 출처" in result["answer"]


def test_근거_없으면_답변_금지_에스컬레이션():
    """환각 방지 핵심 테스트 (스펙 §4.5) — 근거 없으면 LLM을 호출조차 하지 않는다."""
    provider = FakeProvider(["지어낸 답변"])
    node = make_answer_node(provider)
    result = node({"voc_text": "테마 색을 분홍색으로 바꾸고 싶어요", "manual_chunks": []})
    assert result["answer"] == NO_MANUAL_ANSWER
    assert result["escalated"] is True
    assert result["answer_sources"] == []
    assert provider.calls == []  # LLM 미호출 확인


def test_LLM_실패시_폴백_답변():
    provider = FakeProvider([])  # 응답 없음 → 예외
    node = make_answer_node(provider)
    result = node({"voc_text": "x", "manual_chunks": CHUNKS})
    assert result["answer"] == FALLBACK_ANSWER
    assert result["escalated"] is True


def test_provider_None이면_폴백_답변():
    node = make_answer_node(None)
    result = node({"voc_text": "x", "manual_chunks": CHUNKS})
    assert result["answer"] == FALLBACK_ANSWER
    assert result["escalated"] is True


def test_프롬프트에_근거와_VOC_포함():
    prompt = build_answer_prompt("삭제 어떻게 해요?", CHUNKS)
    assert "삭제 어떻게 해요?" in prompt
    assert "할 일 삭제하기" in prompt
    assert "지어내" in prompt  # 환각 금지 지시 포함


def test_retrieve_노드_실제_메뉴얼_검색():
    node = make_retrieve_node()
    result = node({"voc_text": "할 일이 저장되지 않아요", "category": "사용법문의"})
    assert len(result["manual_chunks"]) >= 1
    first = result["manual_chunks"][0]
    assert set(first.keys()) == {"file", "section", "content"}
