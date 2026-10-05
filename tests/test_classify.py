"""classify 단계 테스트 — pydantic-ai 구조화 출력 + 폴백 (스펙 §4.5)."""
from backend.agents import JUDGE_INSTRUCTIONS  # noqa: F401 — import 오류 조기 발견용
from backend.agents import CLASSIFY_INSTRUCTIONS, build_agents
from backend.nodes.classify import FALLBACK_CLASSIFICATION, classify_step
from tests.fakes import FakeModel


def _agents(fake):
    return build_agents(fake.model)


def test_정상_구조화_분류():
    fake = FakeModel([{"category": "버그제보", "priority": "high"}])
    result = classify_step({"voc_text": "앱이 꺼져요"}, _agents(fake))
    assert result == {"category": "버그제보", "priority": "high"}
    assert fake.calls[0] == "앱이 꺼져요"  # 사용자 VOC가 그대로 전달됨 (지시문은 별도 메시지)


def test_허용값_밖은_재시도_후_폴백():
    fake = FakeModel([
        {"category": "문의", "priority": "low"},   # Literal 밖 — 검증 실패
        {"category": "문의", "priority": "low"},   # 재시도 1회 후에도 실패
    ])
    result = classify_step({"voc_text": "x"}, _agents(fake))
    assert result["category"] == "기타"
    assert result["priority"] == "medium"
    assert "error" in result


def test_LLM_실패시_폴백과_에러기록():
    fake = FakeModel([])  # 응답 없음 → 예외
    result = classify_step({"voc_text": "불만 있어요"}, _agents(fake))
    assert result["category"] == "기타"
    assert result["priority"] == "medium"
    assert "error" in result


def test_agents_None_폴백():
    result = classify_step({"voc_text": "x"}, None)
    assert result["category"] == "기타"
    assert result["priority"] == "medium"
    assert result["error"]


def test_지시문에_판정_기준_포함():
    assert "사용법문의" in CLASSIFY_INSTRUCTIONS
    assert "완료한 티켓이 보드에서 사라졌어요" in CLASSIFY_INSTRUCTIONS
