"""미처리 큐 건에 처리 결과 마킹 (스펙 2026-08-23 §6).

사용법: python scripts/gap_resolve.py --voc-id 12 13 --status resolved
종료 코드: 0 전부 성공 / 1 없는 voc_id / 2 잘못된 status
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import SessionLocal, init_database  # noqa: E402
from backend.gap import GAP_STATUSES, mark_gap  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="재료부족 큐 처리 결과 마킹")
    parser.add_argument("--voc-id", nargs="+", type=int, required=True, help="마킹할 VOC id 목록")
    parser.add_argument(
        "--status", required=True, choices=list(GAP_STATUSES),
        help="resolved=메뉴얼·FAQ 반영 / absent=기능 없음 확인 종결",
    )
    args = parser.parse_args()

    init_database()
    for voc_id in args.voc_id:
        try:
            mark_gap(SessionLocal, voc_id, args.status)
        except ValueError as exc:
            print(f"마킹 실패 voc_id={voc_id}: {exc}")
            return 1
        print(f"  마킹 완료 voc_id={voc_id} → {args.status}")
    print(f"결과: {len(args.voc_id)}건 마킹 ({args.status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
