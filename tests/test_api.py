"""FastAPI 엔드포인트 테스트 (스펙 §6.1)."""
from datetime import datetime

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.fakes import FakeProvider

CLASSIFY_HOWTO = '{"category": "사용법문의", "priority": "low"}'
CLASSIFY_BUG = '{"category": "버그제보", "priority": "high"}'
JUDGE_PERFECT = '{"completeness": 5, "accuracy": 5, "fluency": 5, "cause": "해당없음", "reason": ""}'


def make_provider(responses):
    return FakeProvider(responses)


def make_app(provider, session_factory):
    """테스트용 앱 생성"""
    return create_app(provider=provider, session_factory=session_factory)


def test_chat_정상_답변_경로(db_session_factory):
    app = make_app(provider=make_provider([
        CLASSIFY_HOWTO,
        "완료됨 영역을 펼쳐 보세요.\n📖 출처: 03-ui-guide#완료된 할 일 보기",
        JUDGE_PERFECT,
    ]), session_factory=db_session_factory)
    client = TestClient(app)

    resp = client.post("/api/chat", json={"voc_text": "완료한 할 일이 안 보여요", "session_id": "s1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "사용법문의"
    assert data["priority"] == "low"
    assert data["escalated"] is False
    assert data["voc_id"] is not None
    assert data["sources"]
    assert "📖 출처" in data["response"]


def test_chat_에스컬레이션_경로(db_session_factory):
    app = make_app(provider=make_provider([CLASSIFY_BUG, "접수했습니다."]), session_factory=db_session_factory)
    client = TestClient(app)

    resp = client.post("/api/chat", json={"voc_text": "앱이 꺼져요", "session_id": "s2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["escalated"] is True


def test_chat_빈_텍스트_422(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    resp = client.post("/api/chat", json={"voc_text": "", "session_id": "s"})
    assert resp.status_code == 422


def test_llm_미설정시_503(monkeypatch, db_session_factory):
    from backend import config

    monkeypatch.setattr(config.settings, "llm_api_key", "")
    app = make_app(provider=None, session_factory=db_session_factory)
    client = TestClient(app)
    resp = client.post("/api/chat", json={"voc_text": "안녕", "session_id": "s"})
    assert resp.status_code == 503
    assert "LLM_API_KEY" in resp.json()["detail"]


def test_vocs_목록_필터(db_session_factory):
    provider = make_provider([
        CLASSIFY_HOWTO,
        "답변입니다.\n📖 출처: 03-ui-guide#완료된 할 일 보기",
        JUDGE_PERFECT,  # 1번째 채팅(답변 경로)의 백그라운드 채점 응답
        CLASSIFY_BUG,
        "접수했습니다.",
    ])
    app = make_app(provider=provider, session_factory=db_session_factory)
    client = TestClient(app)
    client.post("/api/chat", json={"voc_text": "완료한 할 일이 안 보여요", "session_id": "a"})
    client.post("/api/chat", json={"voc_text": "앱이 꺼져요", "session_id": "b"})

    all_vocs = client.get("/api/vocs").json()
    assert len(all_vocs) == 2

    bugs = client.get("/api/vocs", params={"category": "버그제보"}).json()
    assert len(bugs) == 1
    assert bugs[0]["category"] == "버그제보"

    escalated = client.get("/api/vocs", params={"escalated": "true"}).json()
    assert len(escalated) == 1


def test_voc_단건_조회_404(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    resp = client.get("/api/vocs/9999")
    assert resp.status_code == 404


def test_status_토글(db_session_factory):
    app = make_app(provider=make_provider([CLASSIFY_BUG, "접수했습니다."]), session_factory=db_session_factory)
    client = TestClient(app)
    voc_id = client.post("/api/chat", json={"voc_text": "앱이 꺼져요", "session_id": "s"}).json()["voc_id"]

    resolved = client.patch(f"/api/vocs/{voc_id}/status", json={"status": "resolved"})
    assert resolved.status_code == 200
    assert resolved.json()["escalation_status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None

    reopened = client.patch(f"/api/vocs/{voc_id}/status", json={"status": "open"})
    assert reopened.json()["escalation_status"] == "open"
    assert reopened.json()["resolved_at"] is None

    invalid = client.patch(f"/api/vocs/{voc_id}/status", json={"status": "확인중"})
    assert invalid.status_code == 422


def test_stats(db_session_factory):
    provider = make_provider([
        CLASSIFY_HOWTO,
        "답변입니다.\n📖 출처: 03-ui-guide#완료된 할 일 보기",
        JUDGE_PERFECT,  # 1번째 채팅(답변 경로)의 백그라운드 채점 응답
        CLASSIFY_BUG,
        "접수했습니다.",
    ])
    app = make_app(provider=provider, session_factory=db_session_factory)
    client = TestClient(app)
    client.post("/api/chat", json={"voc_text": "완료 안 보여요", "session_id": "a"})
    client.post("/api/chat", json={"voc_text": "꺼져요", "session_id": "b"})

    stats = client.get("/api/stats").json()
    assert stats["total"] == 2
    assert stats["by_category"]["사용법문의"] == 1
    assert stats["by_category"]["버그제보"] == 1
    assert stats["escalated_open"] == 1
    assert len(stats["by_day"]) == 7


def test_health(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_chat_응답_후_백그라운드_채점(db_session_factory):
    from backend.models import VocRecord

    app = make_app(provider=make_provider([
        CLASSIFY_HOWTO,
        "티켓 삭제 방법 안내입니다.\n📖 출처: 02-managing-todos#티켓 삭제하기",
        JUDGE_PERFECT,
    ]), session_factory=db_session_factory)
    client = TestClient(app)

    resp = client.post("/api/chat", json={"voc_text": "티켓을 어떻게 삭제하나요?", "session_id": "j1"})
    assert resp.status_code == 200
    # TestClient는 응답 직후 백그라운드 태스크를 동기 실행한다

    db = db_session_factory()
    record = db.query(VocRecord).first()
    db.close()
    assert record.judge_total == 15
    assert record.judge_cause == "해당없음"


def test_chat_채점_비활성화(monkeypatch, db_session_factory):
    from backend import config
    from backend.models import VocRecord

    monkeypatch.setattr(config.settings, "judge_enabled", False)
    app = make_app(provider=make_provider([
        CLASSIFY_HOWTO,
        "티켓 삭제 방법 안내입니다.\n📖 출처: 02-managing-todos#티켓 삭제하기",
        JUDGE_PERFECT,  # 채점이 실행되면 이 응답을 소비하여 judge_total=15 기록
    ]), session_factory=db_session_factory)  # 채점이 실행됐다면 judge_total이 기록됨 — 비활성화면 null 유지
    client = TestClient(app)

    resp = client.post("/api/chat", json={"voc_text": "티켓 삭제 방법은?", "session_id": "j2"})
    assert resp.status_code == 200

    db = db_session_factory()
    record = db.query(VocRecord).first()
    db.close()
    assert record.judge_total is None


def test_chat_에스컬레이션은_채점_스킵(db_session_factory):
    from backend.models import VocRecord

    app = make_app(provider=make_provider([
        CLASSIFY_BUG,
        "접수했습니다.",
        JUDGE_PERFECT,  # 채점이 실행되면 이 응답을 소비하여 judge_total=15 기록
    ]), session_factory=db_session_factory)  # 채점이 실행됐다면 judge_total이 기록됨 — 에스컬레이션엔 스킵
    client = TestClient(app)

    resp = client.post("/api/chat", json={"voc_text": "앱이 꺼져요", "session_id": "j3"})
    assert resp.status_code == 200

    db = db_session_factory()
    record = db.query(VocRecord).first()
    db.close()
    assert record.judge_total is None


def _add_voc_direct(session_factory, **kw):
    from backend.models import VocRecord

    defaults = dict(
        session_id="d", voc_text="티켓 삭제 문의", category="사용법문의", priority="low",
        answer="안내 답변", answer_sources=["02-managing-todos#티켓 삭제하기"],
    )
    defaults.update(kw)
    db = session_factory()
    db.add(VocRecord(**defaults))
    db.commit()
    db.close()


def test_vocs_judge_cause_필터(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    _add_voc_direct(db_session_factory, judge_cause="재료부족", judge_total=8)
    _add_voc_direct(db_session_factory, session_id="d2", judge_cause="과정오류", judge_total=10)
    _add_voc_direct(db_session_factory, session_id="d3")  # 미채점

    gaps = client.get("/api/vocs", params={"judge_cause": "재료부족"}).json()
    assert len(gaps) == 1 and gaps[0]["judge_cause"] == "재료부족"
    pending = client.get("/api/vocs", params={"judge_cause": "미채점"}).json()
    assert len(pending) == 1 and pending[0]["judge_total"] is None


def test_stats_채점_집계(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    _add_voc_direct(db_session_factory, judge_scores={"completeness": 5, "accuracy": 5, "fluency": 4}, judge_total=14, judge_cause="해당없음")
    _add_voc_direct(db_session_factory, session_id="d2", judge_total=8, judge_cause="재료부족")   # 저점수 + 재료부족
    _add_voc_direct(db_session_factory, session_id="d3", answer="찾지 못했습니다", answer_sources=None, escalated=True)  # 결정론적 재료부족
    _add_voc_direct(db_session_factory, session_id="d4", answer="접수했습니다", answer_sources=None, escalated=True, category="버그제보")  # 재료부족 아님

    stats = client.get("/api/stats").json()
    assert stats["avg_judge_total"] == 11.0
    assert stats["low_score_count"] == 1
    assert stats["material_gap_count"] == 2  # judge_cause 1건 + 결정론적 1건


def test_stats_채점_0건은_null(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    _add_voc_direct(db_session_factory, answer="접수했습니다", answer_sources=None, escalated=True, category="버그제보")

    stats = client.get("/api/stats").json()
    assert stats["avg_judge_total"] is None
    assert stats["low_score_count"] == 0
    assert stats["material_gap_count"] == 0


def test_voc_단건에_채점_필드_노출(db_session_factory):
    app = make_app(provider=make_provider([]), session_factory=db_session_factory)
    client = TestClient(app)
    _add_voc_direct(db_session_factory, judge_scores={"completeness": 4, "accuracy": 5, "fluency": 5}, judge_total=14, judge_cause="재료부족", judge_reason="복구 절차 없음", judged_at=datetime.utcnow())

    voc = client.get("/api/vocs").json()[0]
    assert voc["judge_total"] == 14
    assert voc["judge_reason"] == "복구 절차 없음"
    assert voc["judged_at"] is not None
