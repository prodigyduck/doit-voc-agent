"""미처리 재료부족 큐 리포트 출력 (스펙 2026-08-23 §6).

사용법: python scripts/gap_report.py  (LLM 키 불필요)
종료 코드: 0
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import SessionLocal, init_database  # noqa: E402
from backend.gap import format_gap_report, iter_gap_open  # noqa: E402


def main() -> int:
    init_database()
    db = SessionLocal()
    try:
        records = iter_gap_open(db)
    finally:
        db.close()
    print(format_gap_report(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
