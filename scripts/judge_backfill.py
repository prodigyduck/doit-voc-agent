"""미채점 답변 건을 일괄 채점 (스펙 2026-08-21 §2).

사용법: .env 설정 후 `python scripts/judge_backfill.py`
종료 코드: 0 완료 / 2 LLM 미설정
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import settings  # noqa: E402
from backend.database import SessionLocal, init_database  # noqa: E402
from backend.judge import get_judge_provider, iter_judge_pending, run_judge  # noqa: E402
from backend.llm import get_llm_provider  # noqa: E402


def main() -> int:
    answer_provider = get_llm_provider(settings)
    if answer_provider is None:
        print("LLM이 설정되지 않았습니다. .env의 LLM_API_KEY를 확인하세요.")
        return 2
    provider = get_judge_provider(settings, answer_provider)

    init_database()
    db = SessionLocal()
    try:
        pending = iter_judge_pending(db)
        ids = [r.id for r in pending]
    finally:
        db.close()

    print(f"채점 대상: {len(ids)}건")
    for voc_id in ids:
        run_judge(voc_id, provider, SessionLocal)
        print(f"  채점 완료 voc_id={voc_id}")
    print(f"결과: {len(ids)}/{len(ids)} 처리")
    return 0


if __name__ == "__main__":
    sys.exit(main())
