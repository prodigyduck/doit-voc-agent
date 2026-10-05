"""LangGraph 조립 + 라우팅 로직 테스트 (스펙 §4.1)."""
from backend.agent import route_after_classify, run_agent
from tests.fakes import FakeProvider

CLASSIFY_HOWTO = '{"category": "사용법문의", "priority": "low"}'
CLASSIFY_BUG = '{"category": "버그제보", "priority": "high"}'


def test_route_규칙():
    assert route_after_classify({"category": "사용법문의"}) == "retrieve"
    assert route_after_classify({"category": "칭찬"}) == "retrieve"
    assert route_after_classify({"category": "불만", "priority": "low"}) == "retrieve"
    assert route_after_classify({"category": "불만", "priority": "high"}) == "escalate"
    assert route_after_classify({"category": "불만", "priority": "medium"}) == "escalate"
    assert route_after_classify({"category": "버그제보"}) == "escalate"
    assert route_after_classify({"category": "기능요청"}) == "escalate"
    assert route_after_classify({"category": "기타"}) == "escalate"


def test_전체_그래프_답변_경로(db_session_factory):
    provider = FakeProvider([
        CLASSIFY_HOWTO,
        "완료한 티켓은 24시간이 지나면 Done 칼럼에서 숨겨집니다. "
        "캘린더 연동 설정에서 다시 확인할 수 있어요.\n"
        "📖 출처: 04-troubleshooting#완료한 티켓이 보드에서 사라졌어요",
    ])
    result = run_agent(
        "완료한 티켓이 보드에서 사라졌어요",
        "s1",
        provider=provider,
        session_factory=db_session_factory,
    )
    assert result["category"] == "사용법문의"
    assert result["escalated"] is False
    assert isinstance(result["voc_id"], int)
    assert "📖 출처" in result["response"]
    assert result["answer_sources"]


def test_전체_그래프_에스컬레이션_경로(db_session_factory):
    provider = FakeProvider([
        CLASSIFY_BUG,
        "접수했습니다. 담당자가 확인할 것입니다.",
    ])
    result = run_agent(
        "앱을 켜면 바로 꺼집니다",
        "s2",
        provider=provider,
        session_factory=db_session_factory,
    )
    assert result["escalated"] is True
    assert result["voc_id"] is not None
    assert "접수했습니다" in result["response"]


def test_그래프_LLM_전체_실패시에도_폴백_응답(db_session_factory):
    provider = FakeProvider([])  # 모든 generate가 실패
    result = run_agent(
        "이상해요",
        "s3",
        provider=provider,
        session_factory=db_session_factory,
    )
    assert result["category"] == "기타"  # classify 폴백
    assert result["escalated"] is True   # 기타 → escalate 경로
    assert result["response"]            # 응답은 존재
