# doit-voc-agent 아키텍처

새 팀원이 코드베이스를 파악하기 위한 구조 문서. 실행 방법은 `README.md`를, 원 설계 의사결정은 `docs/superpowers/specs/`를 참고.

## 1. 시스템 개요

티켓 칸반 보드 앱 **doit**의 사용자 VOC(Voice of Customer)를 처리하는 LLM 에이전트다.

- 채팅으로 받은 VOC를 6유형(사용법문의/버그제보/기능요청/불만/칭찬/기타) × 3우선순위(low/medium/high)로 분류
- 안내로 해결 가능한 유형은 메뉴얼(`manual/`) 검색 근거 답변 생성 + 출처 표기
- 사람 확인이 필요한 유형은 에스컬레이션 → 대시보드에서 상태 관리
- 답변 생성 건은 응답 후 LLM-as-a-Judge가 비동기 채점(3축 점수 + 감점 원인)
- **환각 방지가 핵심 품질 속성**: 근거 없으면 답변 생성을 금지하고 에스컬레이션한다

## 2. 전체 디렉터리 구성

```
doit-voc-agent/
├── backend/            # FastAPI + LangGraph 백엔드
│   ├── main.py         # FastAPI 앱 팩토리 + API 엔드포인트
│   ├── agent.py        # LangGraph 그래프 정의·실행
│   ├── state.py        # AgentState — 파이프라인 상태 스키마
│   ├── nodes/          # 그래프 노드 (파일당 하나, make_*_node 팩토리)
│   ├── llm/            # LLMProvider 추상화 + OpenAI 호환 구현
│   ├── models.py       # SQLAlchemy ORM (voc_records 테이블)
│   ├── schemas.py      # Pydantic 요청/응답 스키마
│   ├── database.py     # 엔진/세션 (PostgreSQL 기본, 테스트는 SQLite)
│   ├── config.py       # .env 기반 Settings 싱글턴
│   ├── constants.py    # 분류 체계 상수
│   ├── judge.py        # LLM-as-a-Judge 비동기 채점
│   ├── observability.py# Langfuse 트레이싱·score 업로드
│   └── manual_retrieval.py  # 메뉴얼 로드 + 간단 검색
├── frontend/           # Vue 3 + Vite (챗 뷰 + 대시보드)
│   └── src/
│       ├── views/      # ChatView, DashboardView
│       ├── components/ # ChatMessage, EscalationTable, StatsCards
│       ├── services/   # api.js — 백엔드 API 클라이언트
│       ├── utils/      # judge.js(점수 표시), markdown.js(미니 렌더러)
│       └── router/     # 라우트 2개 (/, /dashboard)
├── manual/             # doit 사용자 메뉴얼 — 답변의 근거 원천
├── scripts/            # e2e_check, judge_backfill, lint_manual
├── tests/              # pytest (LLM 불필요 — FakeProvider)
├── docs/               # 설계 스펙·구현 계획·본 문서
└── .claude/            # VOC 처리 하네스 (에이전트 4 + 스킬 4)
```

## 3. 백엔드

### 3.1 VOC 처리 파이프라인 (`backend/agent.py`)

```mermaid
graph TD
    START((START)) --> classify
    classify -->|"사용법문의·칭찬, 불만+low"| retrieve
    classify -->|"그 외 전부"| escalate
    retrieve --> generate_answer
    generate_answer --> compose_response
    escalate --> compose_response
    compose_response --> save
    save --> END((END))
```

- 라우팅 규칙 (`route_after_classify`): 사용법문의·칭찬, 불만(low) → `retrieve`, 나머지(버그제보·기능요청·불만 medium/high·기타) → `escalate`
- 그래프와 메뉴얼은 `lru_cache`로 컴파일/로드 1회만 수행 (`_compiled_graph`)
- 노드는 모두 `make_*_node(의존성)` 팩토리 — LLM provider, 메뉴얼 청크, DB 세션 팩토리를 주입받아 테스트가 쉽다

| 노드 | 파일 | 역할 |
|------|------|------|
| classify | `nodes/classify.py` | 프롬프트로 6유형+3우선순위 JSON 분류. 실패 시 기타/medium 폴백 |
| retrieve | `nodes/retrieve.py` | `manual_retrieval.search()` 래핑, 상위 3청크 |
| generate_answer | `nodes/answer.py` | 근거 청크로만 답변 생성. **청크 없으면 LLM 호출 금지 + 에스컬레이션** |
| escalate | `nodes/escalate.py` | 접수 안내 문구 생성. LLM 실패 시 유형별 정적 문구 |
| compose_response | `nodes/respond.py` | answer(출처 확인·부족하면 덧붙임) > escalation_message 우선순위로 최종 응답 조립 |
| save | `nodes/save.py` | VocRecord 저장. **저장 실패해도 응답은 반환** |

노드 간 데이터는 `AgentState`(`state.py`, TypedDict)로 전달되며 파이프라인 진행에 따라 점진적으로 채워진다: `voc_text`/`session_id` → `category`/`priority` → `manual_chunks` → `answer`/`answer_sources` → `response` → `voc_id`.

### 3.2 우아한 열화 규칙 (모든 노드 공통)

LLM 호출은 반드시 `LLMProvider`(`llm/base.py` ABC) 뒤에서 이뤄진다. 각 노드는 LLM 실패·파싱 실패 시 사용자에게 에러를 노출하지 않고 폴백으로 동작한다: classify → 기타/medium, answer → 고정 안내 문구 + 에스컬레이션, escalate → 정적 문구, save → voc_id 없이 계속. provider가 아예 없으면 `/api/chat`만 503을 반환한다.

### 3.3 메뉴얼 검색 (`backend/manual_retrieval.py`)

- 임베딩 없는 간단 검색. 검색 단위는 `##` 섹션(`index.md` 제외)
- 채점: 섹션 제목 토큰 매칭 ×3, 어미 정규화(삭제하나요↔삭제하기) 매칭 ×2, 본문 등장 횟수, 유형별 우선 문서 보너스(+2)
- 유형별 우선 문서: 사용법문의·칭찬 → 01~03, 불만 → 04~05 (버그제보는 검색하지 않는 에스컬레이션 경로)
- 점수 0 이하는 제외, 상위 3개 반환. 벡터 검색 교체 시 `search()` 시그니처 유지

### 3.4 데이터 모델 (`backend/models.py` — `voc_records` 테이블)

| 컬럼 | 설명 |
|------|------|
| `session_id`, `voc_text`, `category`, `priority` | 입력 + 분류 결과 |
| `answer`, `answer_sources`(JSON) | 생성 답변과 출처 목록. 에스컬레이션 경로는 null |
| `escalated`, `escalation_reason`(200자), `escalation_status` | 에스컬레이션 플래그·사유·open/resolved 상태 |
| `judge_scores`(JSON), `judge_total`(3~15), `judge_cause`, `judge_reason`, `judged_at` | 채점 결과. **미채점은 전부 null** |
| `created_at`, `resolved_at` | 타임스탬프 |

DB는 기본 PostgreSQL(`docker compose up -d postgres`). `DATABASE_URL`을 `sqlite://`로 바꾸면 인메모리 SQLite로 동작하며 `database.py`가 커넥션 처리를 분기한다. 테이블은 `init_database()`가 앱 기동 시 생성 (마이그레이션 도구 없음).

### 3.5 API (`backend/main.py`)

| 엔드포인트 | 설명 |
|------------|------|
| `POST /api/chat` | VOC 처리. 응답 후 `JUDGE_ENABLED`면 백그라운드로 채점 (`BackgroundTasks`) |
| `GET /api/vocs` | 이력 목록. 필터: category, escalated, status, judge_cause(특수값 `미채점`=null 건), limit(≤500) |
| `GET /api/vocs/{id}` | 개별 조회 |
| `PATCH /api/vocs/{id}/status` | open ↔ resolved 전환 (resolved 시 `resolved_at` 기록) |
| `GET /api/stats` | 통계: 유형별 집계, 미해결 에스컬레이션, 최근 7일, 채점 평균·저점(≤9) 건수, 재료부족 큐 크기 |
| `GET /health` | LLM 설정 여부 포함 |

앱은 `create_app(provider, session_factory)` 팩토리 — 테스트에서 의존성을 주입한다.

### 3.6 LLM-as-a-Judge 채점 (`backend/judge.py`)

- 채점 대상은 **답변 생성 경로만**(`answer_sources` + `answer` 존재). 에스컬레이션 건은 채점하지 않는다
- 3축 각 1~5점: completeness(완결성), accuracy(정확성 — 환각 시 1점), fluency(유창성)
- 감점 원인(cause): 재료부족(출처에 정보가 없음, 정직한 부정 안내 포함) / 과정오류(있는데 놓침·잘못 인용) / 해당없음
- 응답 후 백그라운드 실행이라 실패해도 사용자 영향 없음. 파싱 실패·LLM 실패는 미채점(null) 유지
- `JUDGE_MODEL`이 비어 있으면 답변 모델을 그대로 재사용
- `scripts/judge_backfill.py`로 미채점 건을 일괄 재채점할 수 있다

### 3.7 관측 (`backend/observability.py`, Langfuse)

- 활성 조건: `LANGFUSE_ENABLED=true` + 공개/비밀 키. 꺼져 있으면 핸들러를 만들지 않아 행동 변화가 없다
- 활성 시 `/api/chat`마다 세션 단위 트레이스(`voc_pipeline`)를 붙여 그래프 노드 실행이 기록되고, 채점 결과가 트레이스에 `judge_total` score로 업로드된다
- 관측 실패는 콘솔 로그만 남기고 파이프라인에 예외를 전파하지 않는다

## 4. 프론트엔드 (`frontend/`, Vue 3 + Vite)

| 경로 | 역할 |
|------|------|
| `views/ChatView.vue` | VOC 채팅. 프리셋 질문 칩 제공, 세션 ID는 sessionStorage에서 발급·유지 |
| `views/DashboardView.vue` | 통계 카드 + 에스컬레이션 테이블 + 유형/원인 필터, 상태 토글 |
| `components/ChatMessage.vue` | 개별 메시지 렌더링 |
| `components/EscalationTable.vue` | VOC 목록 표 — open/resolved 라벨, 채점 점수 표시 |
| `components/StatsCards.vue` | `/api/stats` 카드 (총 건수, 미해결, 채점 평균, 재료부족 등) |
| `services/api.js` | 백엔드 API 클라이언트. 기본 같은 오리진 상대경로, `VITE_API_BASE`로 직접 지정 가능 |
| `utils/markdown.js` | 간단 마크다운 렌더러 (외부 의존 없음) |
| `utils/judge.js` | 채점 점수·원인 표시 헬퍼 (`.spec.js`가 붙은 것들은 vitest 대상) |

`vite.config.js`가 `/api`를 `http://localhost:8000`으로 프록시해 한 오리진으로 동작한다 (터널/역방향 프록시 환경 고려).

## 5. VOC 처리 하네스 (`.claude/`)

이 저장소의 기능 개발은 멀티 에이전트 하네스로 진행한다. 트리거는 `doit-orchestrator` 스킬 ("구현 시작", "다음 단계 진행" 등).

| 에이전트 (`.claude/agents/`) | 책임 | HOW 스킬 |
|------------------------------|------|----------|
| manual-writer | 메뉴얼 작성 | manual-authoring |
| backend-engineer | 그래프/API | voc-pipeline |
| frontend-engineer | 챗/대시보드 | dashboard-ui |
| qa-engineer | 품질 게이트 | — |

진행 방식: 요청을 의존 순서(메뉴얼 ↔ LLM 추상화 병렬 → manual_retrieval → 그래프 → API → 프론트 → E2E)에 따라 단위 작업으로 분해하고, 각 작업 완료 시 qa-engineer 게이트(pytest + lint + build)를 통과해야 커밋한다.

## 6. 테스트 전략

| 계층 | 도구 | 특징 |
|------|------|------|
| 백엔드 단위 | pytest (`tests/`) | LLM 불필요 — `tests/fakes.py`의 `FakeProvider`가 예약 응답을 순서대로 반환. `conftest.py`가 DB를 인메모리 SQLite로 강제하고 Langfuse를 비활성화 |
| 메뉴얼 구조 | `scripts/lint_manual.py` | 문서 5종 존재, 섹션 중복 금지, troubleshooting 3단 구조(증상/원인/해결), index 링크 검증 |
| 프론트엔드 | vitest | utils 로직 단위 테스트 (`*.spec.js`) |
| E2E | `scripts/e2e_check.py` | 실제 LLM으로 대표 VOC 6개 검증 (.env 필요). 분류 기대치 + 에스컬레이션 기대치 확인 |

테스트 파일은 모듈별 대응(`test_classify.py`, `test_judge.py` …)이며 `pytest -q`로 전체 실행.

## 7. 환경·설정

`.env` (`cp .env.example .env`):

| 키 | 기본값 | 설명 |
|----|--------|------|
| `DATABASE_URL` | `postgresql://doit:doit@localhost:5432/doit_agent` | docker-compose의 postgres와 일치 |
| `LLM_PROVIDER` | `openai_compat` | 현재 유일한 구현체 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 공식 | OpenAI 호환이면 무엇이든 교체 가능. 키 없으면 provider=None → 우아한 열화 |
| `JUDGE_ENABLED` | `true` | 채점 on/off |
| `JUDGE_MODEL` | (빈) | 빈 값이면 답변 모델 재사용 |
| `LANGFUSE_ENABLED` | `false` | 키 2개와 함께 켜야 활성 |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | — | Langfuse 접속 정보 |

기타: 루트의 `doit_voc_agent.db`는 로컬 실행 흔적(`*.db` gitignored). 로그 파일을 만들지 않고 콘솔 출력만 사용한다. 커밋은 conventional commits 한국어 제목.

## 8. 관련 문서

- 설계 스펙: `docs/superpowers/specs/2026-08-18-doit-voc-agent-design.md` (MVP), `2026-08-21-judge-design.md` (채점), `2026-08-23-gap-queue-design.md` (재료부족 큐)
- 구현 계획: `docs/superpowers/plans/`
- 대상 앱: `~/git/doit` (티켓 칸반 보드)
