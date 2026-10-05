"""실제 LLM으로 대표 VOC 6개를 처리해 MVP 품질 게이트 검증 (스펙 §8 E2E).

사용법: .env 설정 후 `python scripts/e2e_check.py`
종료 코드: 0 통과 / 1 시나리오 실패 / 2 LLM 미설정
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agent import run_agent  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.database import SessionLocal, init_database  # noqa: E402
from backend.judge import JUDGE_CAUSES, get_judge_provider, run_judge  # noqa: E402
from backend.llm import get_llm_provider  # noqa: E402
from backend.models import VocRecord  # noqa: E402

# (VOC, 기대 유형(None=무관), 기대 에스컬레이션 여부)
SCENARIOS = [
    ("완료한 티켓이 보드에서 사라졌어요. 어디서 확인하나요?", "사용법문의", False),
    ("티켓을 어떻게 삭제하나요?", "사용법문의", False),
    ("완료한 티켓이 사라졌어요", "사용법문의", False),  # 진술형도 안내로 해결
    ("앱을 켜면 바로 꺼집니다. 고쳐주세요.", "버그제보", True),
    ("다크 모드도 추가해 주세요.", "기능요청", True),
    ("화면 테마 색을 분홍색으로 바꾸고 싶어요.", None, True),  # 메뉴얼에 없는 기능 → 에스컬레이션
]


def main() -> int:
    provider = get_llm_provider(settings)
    if provider is None:
        print("LLM이 설정되지 않았습니다. .env의 LLM_API_KEY를 확인하세요.")
        return 2

    init_database()
    failures = 0
    for i, (voc, expected_category, expected_escalated) in enumerate(SCENARIOS, 1):
        result = run_agent(
            voc_text=voc,
            session_id=f"e2e-{i}",
            provider=provider,
            session_factory=SessionLocal,
        )
        category = result.get("category")
        escalated = bool(result.get("escalated"))
        ok_category = expected_category is None or category == expected_category
        ok_escalated = escalated == expected_escalated
        ok_judge = True
        judge_line = ""
        if result.get("answer_sources") and result.get("voc_id"):
            run_judge(result["voc_id"], get_judge_provider(settings, provider), SessionLocal)
            db = SessionLocal()
            try:
                rec = db.query(VocRecord).filter(VocRecord.id == result["voc_id"]).first()
            finally:
                db.close()
            ok_judge = (
                rec is not None
                and rec.judge_total is not None
                and rec.judge_cause in JUDGE_CAUSES
            )
            if rec is not None and rec.judge_total is not None:
                judge_line = (
                    f"\n       채점={rec.judge_total}/15 원인={rec.judge_cause}"
                    f" (근거: {rec.judge_reason})"
                )
        status = "PASS" if (ok_category and ok_escalated and ok_judge) else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"[{status}] VOC {i}: {voc}")
        print(f"       분류={category} (기대={expected_category or '무관'}) "
              f"에스컬레이션={escalated} (기대={expected_escalated})")
        print(f"       응답: {(result.get('response') or '')[:120]}")
        print(f"       출처: {result.get('answer_sources') or []}")
        if judge_line:
            print(judge_line)
        print()

    print(f"결과: {len(SCENARIOS) - failures}/{len(SCENARIOS)} 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
