from backend.nodes.classify import (
    FALLBACK_CLASSIFICATION,
    make_classify_node,
    parse_classification,
)
from tests.fakes import FakeProvider


def test_정상_JSON_파싱():
    result = parse_classification('{"category": "버그제보", "priority": "high"}')
    assert result == {"category": "버그제보", "priority": "high"}


def test_JSON_앞뒤_설명_허용():
    result = parse_classification(
        '분류 결과입니다\n{"category": "칭찬", "priority": "low"}\n감사합니다'
    )
    assert result["category"] == "칭찬"


def test_잘못된_유형은_폴백():
    result = parse_classification('{"category": "문의", "priority": "low"}')
    assert result == dict(FALLBACK_CLASSIFICATION)


def test_파싱_불가_출력은_폴백():
    assert parse_classification("죄송합니다 무슨 뜻인지 모르겠어요") == dict(FALLBACK_CLASSIFICATION)


def test_노드_정상_동작():
    provider = FakeProvider(['{"category": "사용법문의", "priority": "low"}'])
    node = make_classify_node(provider)
    result = node({"voc_text": "완료는 어떻게 하나요?"})
    assert result == {"category": "사용법문의", "priority": "low"}
    assert "사용법문의" in provider.calls[0]  # 프롬프트에 분류 기준 포함 확인


def test_노드_LLM_실패시_폴백과_에러기록():
    provider = FakeProvider([])  # 응답 없음 → 예외
    node = make_classify_node(provider)
    result = node({"voc_text": "불만 있어요"})
    assert result["category"] == "기타"
    assert result["priority"] == "medium"
    assert "error" in result


def test_노드_provider_None_폴백():
    node = make_classify_node(None)
    result = node({"voc_text": "x"})
    assert result["category"] == "기타"
