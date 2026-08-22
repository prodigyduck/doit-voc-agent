# Phase 2: LLM-as-a-Judge 설계 (doit-voc-agent)

**일자**: 2026-08-21
**상태**: 승인됨 (사용자 확정 2026-08-21)
**선행**: MVP(2026-08-18 스펙)·검색 품질 개선·doit 전환 완료

## 1. 목표·범위

VOC 답변 품질을 자동 채점해 관측하고, 감점 원인을 **재료부족**(메뉴얼에 내용 없음)과
**과정오류**(파이프라인이 출처를 놓침/왜곡)로 분류한다. 재료부족 목록은 Phase 3
(자동 매뉴얼 생성)의 입력 큐가 된다.

**범위 내**: 비동기 채점, 점수·원인 저장, stats/vocs API 확장, 대시보드 표시·필터,
미채점 백필 스크립트, E2E 채점 단계.

**범위 외(YAGNI)**: 저점수 자동 재생성 루프, Phase 3 매뉴얼 생성, 별도 워커/큐 인프라,
채점 전용 API 엔드포인트.

## 2. 아키텍처

```
POST /api/chat
  ├─ run_agent()            — 기존 LangGraph 파이프라인, 무변경
  │    응답 즉시 반환 (지연 0초)
  └─ BackgroundTasks: run_judge(voc_id)   — 신규, 응답 후 비동기
```

- 핵심 그래프(`backend/agent.py`)·기존 노드는 수정하지 않는다.
- 신규 모듈 `backend/judge.py`:
  - `JUDGE_PROMPT` — 채점 프롬프트(§4)
  - `parse_judge(text) -> Optional[JudgeResult]` — JSON 추출·검증 (classify 파서 패턴 재사용)
  - `should_judge(record) -> bool` — 채점 대상 판별
  - `run_judge(voc_id, provider, session_factory) -> None` — 레코드 로드→채점→업데이트
- `backend/main.py`의 `/api/chat` 핸들러가 응답 후 `background_tasks.add_task(run_judge, ...)`
  로 등록한다. `JUDGE_ENABLED=false`이면 등록하지 않는다.
- 미채점 보완: `scripts/judge_backfill.py` — `judge_scores IS NULL` && 채점 대상인 건을
  순회 채점. 종료 코드: 0 전부 처리 / 2 LLM 미설정.

## 3. 데이터 모델

`VocRecord`(`backend/models.py`)에 컬럼 5개 추가:

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `judge_scores` | JSON, nullable | `{"completeness": 1-5, "accuracy": 1-5, "fluency": 1-5}` |
| `judge_total` | Integer, nullable | 세 축 합계 3~15 |
| `judge_cause` | String(20), nullable | `"재료부족"` \| `"과정오류"` \| `"해당없음"` (미채점=null) |
| `judge_reason` | String(200), nullable | 감점 근거 한 줄 (200자 절단, 대시보드 툴팁용) |
| `judged_at` | DateTime, nullable | 채점 완료 시각 |

**채점 대상**: `answer_sources`가 null이 아니면서 빈 배열도 아닌 건 (답변 생성 경로 — 사용법문의/칭찬/불만-low
중 청크를 찾은 경우). 에스컬레이션 접수 경로(버그제보·기능요청 등)의 안내 문구는 채점하지
않는다.

**재료부족 큐** (Phase 3 입력):
- `judge_cause = '재료부족'` — 채점 결과 판정, 또는
- 결정론적 판정: `category = '사용법문의'` && `escalated = True` && `answer_sources`가 비어 있음(null 또는 빈 배열)
  (메뉴얼에 해당 내용이 없어 "찾지 못했습니다"로 넘어간 건 — LLM 없이 재료부족 확정).
  칭찬·불만의 무청크는 품질 신호가 약해 제외한다.

**마이그레이션**: `init_database()`의 `create_all`은 기존 테이블에 컬럼을 추가하지 않는다.
아직 배포 전이므로 로컬 dev DB(sqlite 파일)는 삭제 후 재생성으로 해결한다. 신규 환경은
자동 스키마. 운영 배포 시점에만 ALTER/마이그레이션 도구를 별도 논의한다.

## 4. 채점 상세

**입력**(JUDGE_PROMPT에 포함): 원본 VOC, 생성된 답변, 출처 청크 원문
(`answer_sources`의 `file#section`을 `load_manual()` 청크에서 역참조한 content).

**출력 JSON** (다른 설명 없이 JSON만 출력):
```json
{"completeness": 4, "accuracy": 5, "fluency": 5, "cause": "재료부족", "reason": "삭제 복구 절차가 출처에 없어 완결성 감점"}
```

**축 정의** (프롬프트에 명시):
- `completeness`(완결성): VOC 질문에 답변이 충분한가 — 질문이 요구하는 해결책이 출처에 없어 정직하게 안내만 한 답변은 질문을 해결하지 못했으므로 반드시 감점
- `accuracy`(정확성): 출처 청크와 일치하는가 — 환각(출처에 없는 내용 서술)은 1점
- `fluency`(유창성): 문장이 자연스럽고 톤이 고객 응대에 적합한가

**원인 정의** (감점 축이 있을 때 1개 선택):
- `재료부족`: 출처 청크에 필요한 정보가 없어 답변이 불완전 — 해결책이 출처에 없다는 정직한 부정 안내(예: "메뉴얼에 없음")도 이 원인으로 판정
- `과정오류`: 출처에 정보가 있는데 답변이 놓치거나 잘못 인용·문장이 깨짐
- `해당없음`: 감점 축 없음

**폴백**: LLM 호출 실패·JSON 파싱 실패·값 검증 실패 → 미채점(컬럼 null 유지) + 서버 로그.
사용자 응답은 이미 반환된 뒤므로 사용자 영향 0. 재시도는 하지 않는다(백필 스크립트로 보완).

## 5. 설정 (backend/config.py)

| 키 | 기본값 | 의미 |
|---|---|---|
| `JUDGE_ENABLED` | `true` | false면 백그라운드 채점 등록 안 함 |
| `JUDGE_MODEL` | `LLM_MODEL` 값 | 설정 시 채점용 프로바이더를 같은 팩토리로 별도 생성 |

채점 프로바이더는 `get_llm_provider` 계열 팩토리를 재사용한다(새 의존성 없음).

## 6. API

- `GET /api/stats` — 기존 응답에 키 추가(기존 키 유지, 제거 없음):
  `avg_judge_total`(소수 1자리, 채점 건 기준, 0건이면 null), `low_score_count`
  (judge_total ≤ 9), `material_gap_count`(재료부족 큐 건수 — §3 두 분류는 판정 경로가
  달라 상호배타이므로 단순 합산)
- `GET /api/vocs?judge_cause=재료부족` — 기존 유형/에스컬레이션 필터와 동일 패턴의 필터 추가.
  값: `재료부족`|`과정오류`|`해당없음`|`미채점`(null 매칭)

## 7. 프론트 대시보드 (frontend/src/views/DashboardView.vue)

- VOC 테이블 행: 총점 배지 `12/15` + 원인 태그(재료부족=주황, 과정오류=빨강, 해당없음/미채점=숨김)
- 통계 카드 2개 추가: 평균 답변 점수(평균/15), 재료부족 큐 건수
- 기존 필터 드롭다운에 "재료부족" 옵션 추가
- 기존 디자인 톤·컴포넌트 패턴 유지

## 8. E2E·게이트

- `scripts/e2e_check.py`: 답변 생성 시나리오에 채점 단계 추가 — `run_agent` 후 `run_judge`
  호출해 점수·원인을 출력, 채점 결과 존재(judge_total null 아님) && 원인 유효을 PASS 조건에 포함
- 게이트(기존 유지): `pytest -q` 전체, `lint_manual.py`, 프론트 `npm test && npm run build`,
  라이브 `e2e_check.py`
- 수동 확인: 채팅 응답 후 대시보드에서 점수 배지·재료부족 필터 실동작

## 9. 테스트 계획

| 대상 | 검증 |
|---|---|
| `parse_judge` | 유효 JSON, 무효 JSON(폴백 null), 점수 경계(1·5·6 거부), cause 화이트리스트 |
| `should_judge` | answer_sources 있음→True, 없음(에스컬레이션)→False |
| `run_judge` | FakeProvider 캔 응답 → 레코드 5컬럼 저장 확인, provider 실패 → null 유지 |
| 결정론적 재료부족 | 사용법문의+무출처+에스컬레이션 → 큐 카운트 포함 |
| `/api/stats` | 평균·저점수·재료부족 계산 (채점 0건 → null/0) |
| `/api/vocs` | judge_cause 필터·미채점 매칭 |
| 프론트 | 배지·태그 렌더링, 필터 옵션 (vitest) |
| 백필 스크립트 | 미채점 대상만 채점, 이미 채점 건 미변경 |

테스트 전반에 기존 FakeProvider·db_session 픽스처 패턴을 재사용한다.

## 10. 추후 확장 (참고 — 이번 범위 아님)

Phase 3에서 재료부족 큐를 소비해 Playwright·소스코드 기반 매뉴얼 초안을 생성하고,
관리자 승인 후 `manual/`에 반영한다. 저점수 자동 재생성은 데이터가 쌓인 뒤 재검토한다.
