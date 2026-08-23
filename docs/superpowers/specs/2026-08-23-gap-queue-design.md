# Phase 3: 재료부족 큐 소비·매뉴얼 보강 설계 (doit-voc-agent)

**일자**: 2026-08-23
**상태**: 승인됨 (사용자 확정 2026-08-23)
**선행**: MVP(2026-08-18)·Phase 2 LLM-as-a-Judge(2026-08-21) 완료,
채점 프롬프트 완결성 감점 규칙(5f4e7cf) 적용

## 1. 목표·범위

Phase 2가 만든 재료부족 큐를 소비해 메뉴얼·FAQ를 보강하는 **하네스 반자동 사이클**을
만든다. 초안은 manual-writer 에이전트가 doit 소스 코드 근거로 작성하고, 사람(사용자)
리뷰·qa-engineer 게이트를 통과해야 `manual/`에 반영된다.

**성공 기준**: 보강된 주제의 동일 VOC가 재접수되면 ①출처 있는 해결 안내 또는
②"제공하지 않습니다" 출처 있는 부정 안내를 받고, ③해당 큐 건이 마킹되어
미처리 카운트에서 사라진다.

**범위 내**: `gap_status` 컬럼, 큐 predicate 모듈(`backend/gap.py`),
stats/vocs 집계 정합화, 스크립트 2종(`gap_report.py`·`gap_resolve.py`),
doit-orchestrator 스킬 큐 소비 절차, E2E 시나리오 7.

**범위 외(YNGNI)**: 대시보드 마킹 UI·PATCH API(운영 니즈 발생 시 접근법 B/C로 확장),
`VocOut`의 `gap_status` 노출, VOC 주제 자동 클러스터링, 저점수 자동 재생성,
런타임(백엔드 LLM) 초안 생성, 백필 재채점.

**확정된 설계 결정** (2026-08-23 사용자 확정):
- 자동화 수준: **하네스 반자동** — 초안=에이전트, 승인=사람
- 앱에 없는 기능: **FAQ 문서화 + 마킹** — 05-faq "제공하지 않는 기능" 섹션
- 큐 상태 추적: **DB 상태 컬럼**

## 2. 아키텍처

```
[런타임 — 기존 Phase 2 무변경]
  judge 판정: judge_cause='재료부족'                    ┐ 재료부족 큐 후보
  결정론적: 사용법문의 + escalated + 무출처(answer_sources 비어 있음) ┘
        │
        ▼  gap_status IS NULL 인 건 = 미처리 큐 (파생, 저장 아님)
[개발 세션 하네스 — doit-orchestrator "큐 소비" 절차]
  1. 오케스트레이터: python scripts/gap_report.py
  2. manual-writer: 리포트 건 → doit 코드 근거 수집 → 메뉴얼/FAQ 초안
  3. 사용자 리뷰 + qa-engineer 게이트 → 커밋
  4. python scripts/gap_resolve.py → resolved|absent 마킹, 원장 기록
        │
        ▼
[사이클 닫힘] 다음 동일 VOC → 출처 있는 답변 → 재료부족 판정 자체가 발생하지 않음
```

- 그래프(`backend/agent.py`)·노드(`backend/nodes/*`)·`backend/judge.py` **무변경**.
- 신규 모듈 `backend/gap.py`가 큐 정의의 단일 진실 공급원(§4).
- 런타임 변경은 집계·필터의 **의미 정합화**뿐 (시그니처·프론트 무변경).

## 3. 데이터 모델

`VocRecord`(`backend/models.py`)에 컬럼 1개 추가 — judged_at 라인 뒤:

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `gap_status` | String(12), nullable | `null`(미처리) \| `'resolved'`(메뉴얼·FAQ 반영) \| `'absent'`(기능 없음 확인 종결) |

- **'open' 상태는 저장하지 않는다** — 미처리는 "재료부족 판정 && gap_status IS NULL"로
  파생한다. 채점·저장 경로가 gap_status를 쓰지 않으므로 nodes·judge가 무변경으로 유지된다.
- 값 화이트리스트 `('resolved', 'absent')` — 스크립트·모듈에서 검증. 마킹 근거 메모는
  컬럼 대신 커밋 메시지·진행 원장에 남긴다(컬럼 최소화).
- 마이그레이션: judge 컬럼 때와 동일 — `create_all`은 기존 테이블에 컬럼을 추가하지
  않으므로 로컬 dev sqlite는 삭제 후 재생성. 운영 ALTER는 배포 시점 별도 논의.

## 4. 큐 정의 — backend/gap.py (신규)

**모든 큐 소비자(카드·필터·리포트·마킹)는 이 predicate로만 큐를 정의한다.**
정의 중복 금지 — Phase 2 최종 리뷰 "큐 소비자는 카드 정의 사용" 권고의 구체화.

```python
GAP_RESOLVED = "resolved"
GAP_ABSENT = "absent"
GAP_STATUSES = (GAP_RESOLVED, GAP_ABSENT)

def is_material_gap(record) -> bool:
    """재료부족 판정 — Phase 2 카드 정의 그대로 (judge 스펙 §3, 2026-08-23 문구 교정판)."""
    return (
        record.judge_cause == "재료부족"
        or (record.category == "사용법문의" and record.escalated and not record.answer_sources)
    )

def is_gap_open(record) -> bool:
    """미처리 큐 — 재료부족 판정 && 마킹 없음."""
    return is_material_gap(record) and record.gap_status is None

def iter_gap_open(db) -> List[VocRecord]:  # 생성일 순, 리포트·집계용
def mark_gap(session_factory, voc_id: int, status: str) -> None  # 검증 후 저장. ValueError: 화이트리스트 밖 / 없는 voc_id
def format_gap_report(records) -> str      # 순수 함수 — 마크다운 리포트 (테스트 대상)
```

## 5. API — 의미 정합화 (시그니처·프론트 무변경)

- `GET /api/stats`의 `material_gap_count` → `is_gap_open` 집계으로 교체.
  마킹된 건은 카드에서 사라진다 — 큐 소비가 대시보드에서 관측 가능 (Phase 3 성과 지표).
  마킹 미존재 시 수치는 기존과 동일(두 판정 경로는 상호배타 — judge 스펙 §6).
- `GET /api/vocs?judge_cause=재료부족` → **미처리 큐 전체** 반환으로 진화:
  기존 judge 판정 건만 잡혀 결정론적 건이 카드와 어긋났던 것을 바로잡는다
  (judge 판정 미마킹 + 결정론적 미마킹). `미채점` 필터 등 나머지 값은 무변경.
- 프론트는 코드·라벨 무변경 — 숫자·목록만 정확해진다. `VocOut` 확장 없음.

## 6. 스크립트 (judge_backfill.py 패턴 재사용)

**`scripts/gap_report.py`** — 미처리 큐 마크다운 리포트. LLM 키 불필요.

```
## 재료부족 미처리 큐 — N건
### voc_id=12 [judge] 2026-08-23 사용법문의
- 질문: CSV로 할 일 목록을 내보내고 싶은데 어떻게 하죠?
- 답변(200자): 죄송하지만 메뉴얼에서 찾지 못했습니다…
- 판정 근거: 메뉴얼 출처에 CSV 내보내기 방법이 없어 해결책을 제공하지 못함
```

- `[judge]`/`[결정론적]`으로 판정 경로 구분 표시. 종료코드 0 (0건이면 "미처리 큐 없음").

**`scripts/gap_resolve.py`** — `--voc-id N [N ...] --status resolved|absent` (voc-id 복수 허용).
종료코드: 0 전부 성공 / 1 없는 voc_id / 2 화이트리스트 밖 status. 즉시 커밋.

## 7. 하네스 절차 (doit-orchestrator 스킬에 "재료부족 큐 소비" 추가)

트리거: "큐 처리", "재료부족 큐 소비" 등.

1. **오케스트레이터**: `python scripts/gap_report.py` 실행해 리포트 확보 (0건이면 종료 보고)
2. **manual-writer 위임** — 브리프에 리포트 해당 건 전달, manual-authoring 스킬으로 근거 수집:
   - 기능이 doit 코드에 존재 → 적절한 문서(01~04)의 `##` 섹션 추가·보강.
     필요시 doit 앱 실행·Playwright 실동작 확인 허용
   - 기능 부재 확인 → `05-faq.md` "제공하지 않는 기능" 섹션에 항목화
     (동일 문의가 다음엔 출처 있는 부정 안내를 받도록)
3. **qa-engineer 게이트** + 사용자 리뷰 → 커밋 (기존 게이트 4종 + 라이브 E2E)
4. **마킹**: `gap_resolve.py --voc-id … --status resolved|absent`, 진행 원장 기록

런타임 코드는 이미 구현된 상태이므로 이 단계의 backend-engineer·frontend-engineer
참여는 불필요 (예외: 게이트 실패 시 수정 위임).

## 8. E2E·게이트

- `scripts/e2e_check.py` **시나리오 7** 추가: "CSV로 할 일 목록을 내보내는 방법은?"
  (메뉴얼에 없는 기능 사용법 문의). PASS 조건:
  ①사용법문의 분류 ②정직한 안내(지어내지 않음) ③해당 레코드 `is_gap_open` 참
  ④`gap_report` 출력에 해당 voc_id 포함 — 채점 프롬프트 감점 규칙(5f4e7cf)의
  라이브 회귀 검증을 겸한다.
- 게이트(기존 유지): `pytest -q`, `lint_manual.py`, 프론트 `npm test && npm run build`,
  라이브 `e2e_check.py` 7/7.
- 수동 확인: 대시보드 재료부족 카드·"재료부족" 필터 목록이 gap_report 건수와 일치,
  마킹 후 카드 감소.

## 9. 테스트 계획

| 대상 | 검증 |
|---|---|
| `is_material_gap` | judge 판정 → 참 / 결정론적(사용법문의+escalated+무출처) → 참 / 버그제보 에스컬레이션·칭찬 무출처 → 거짓 행렬 |
| `is_gap_open` | 마킹 없음 → 참 / resolved·absent 마킹 → 거짓 / 재료부족 아닌 건 → 거짓 |
| `mark_gap` | 정상 저장·커밋 / 화이트리스트 밖 ValueError / 없는 voc_id ValueError |
| `format_gap_report` | 건별 필드(voc_id·판정 경로·질문·근거) 포함 / 0건 안내 |
| `/api/stats` | 마킹 전 후 material_gap_count 감소 (마킹 없으면 기존 수치와 동일) |
| `/api/vocs?judge_cause=재료부족` | 결정론적 건 포함 + 마킹 건 제외 (기존 필터 테스트 갱신) |
| 스크립트 | `py_compile` + 종료코드 (코어 로직은 gap.py 테스트로 커버 — judge_backfill 패턴) |
| E2E 시나리오 7 | 라이브 — 컨트롤러 게이트에서 검증 |

기존 FakeProvider·db_session 픽스처 패턴 재사용. Python 3.9 가상환경(내장 제네릭
타이핑 금지) 제약 유지.

## 10. 추후 확장 (참고 — 이번 범위 아님)

- 대시보드 마킹 UI·`PATCH /api/vocs/{id}/gap-status` (접근법 B/C — 운영 니즈 발생 시)
- `VocOut.gap_status` 노출·재료부족 탭 상태 배지
- 미처리 큐 주제 클러스터링(유사 질문 그룹핑)으로 리포트 정리
- 저점수(judge_total ≤ 9) 과정오류 건의 답변 품질 개선 루프
