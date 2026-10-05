from backend.agents import build_agents
from backend.models import VocRecord
from backend.nodes.escalate import ESCALATION_MESSAGES, escalate_step
from backend.nodes.respond import respond_step
from backend.nodes.save import save_state
from tests.fakes import FakeModel


def _agents(fake):
    return build_agents(fake.model)


def test_escalate_정적_문구_agents없음():
    result = escalate_step({"voc_text": "앱이 꺼져요", "category": "버그제보"}, None)
    assert result["escalated"] is True
    assert result["escalation_message"] == ESCALATION_MESSAGES["버그제보"]
    assert "버그제보" in result["escalation_reason"]


def test_escalate_LLM_문구_생성():
    fake = FakeModel(["접수했습니다. 빠르게 확인하겠습니다."])
    result = escalate_step(
        {"voc_text": "버그", "category": "버그제보"}, _agents(fake)
    )
    assert result["escalation_message"] == "접수했습니다. 빠르게 확인하겠습니다."


def test_escalate_LLM_실패시_정적_폴백():
    fake = FakeModel([])  # 응답 없음 → 예외
    result = escalate_step({"voc_text": "버그", "category": "버그제보"}, _agents(fake))
    assert result["escalation_message"] == ESCALATION_MESSAGES["버그제보"]


def test_respond_답변_있으면_답변_그대로():
    result = respond_step({
        "answer": "이렇게 하세요\n📖 출처: 03-ui-guide#할 일 삭제하기",
        "answer_sources": ["03-ui-guide#할 일 삭제하기"],
    })
    assert result["response"].startswith("이렇게 하세요")


def test_respond_출처_누락시_덧붙임():
    result = respond_step({"answer": "이렇게 하세요", "answer_sources": ["03-ui-guide#할 일 삭제하기"]})
    assert "03-ui-guide#할 일 삭제하기" in result["response"]


def test_respond_에스컬레이션만_있으면_안내문구():
    result = respond_step({"escalated": True, "escalation_message": "전달했습니다"})
    assert result["response"] == "전달했습니다"


def test_respond_아무것도_없으면_기본_안내():
    result = respond_step({})
    assert result["response"]  # 빈 문자열 아님


def test_save_저장(db_session_factory):
    result = save_state({
        "voc_text": "불만 있어요",
        "session_id": "s1",
        "category": "불만",
        "priority": "low",
        "escalated": True,
    }, db_session_factory)
    assert isinstance(result["voc_id"], int)

    db = db_session_factory()
    record = db.query(VocRecord).first()
    db.close()
    assert record.escalated is True
    assert record.escalation_status == "open"


def test_save_답변_경로_저장(db_session_factory):
    result = save_state({
        "voc_text": "완료 어떻게 해요?",
        "session_id": "s2",
        "category": "사용법문의",
        "priority": "low",
        "answer": "체크박스를 누르세요",
        "answer_sources": ["03-ui-guide#완료된 할 일 보기"],
        "escalated": False,
    }, db_session_factory)
    assert isinstance(result["voc_id"], int)

    db = db_session_factory()
    record = db.query(VocRecord).filter_by(session_id="s2").first()
    db.close()
    assert record.answer == "체크박스를 누르세요"
    assert record.escalated is False


def test_save_에스컬레이션_사유_200자_초과시_절단(db_session_factory):
    result = save_state({
        "voc_text": "앱이 꺼져요",
        "session_id": "s3",
        "category": "버그제보",
        "priority": "high",
        "escalated": True,
        "escalation_reason": "x" * 500,  # LLM 실패 메시지처럼 200자 초과
    }, db_session_factory)
    assert isinstance(result["voc_id"], int)

    db = db_session_factory()
    record = db.query(VocRecord).filter_by(session_id="s3").first()
    db.close()
    assert len(record.escalation_reason) == 200


def test_save_실패해도_폭발하지_않음():
    def broken_factory():
        raise RuntimeError("db down")

    result = save_state({"voc_text": "x"}, broken_factory)
    assert result["voc_id"] is None
    assert "error" in result
