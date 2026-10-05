# doit-voc-agent

티켓 칸반 보드 앱 **doit**의 사용자 VOC(Voice of Customer)를 처리하는 LLM 에이전트.

- 채팅으로 VOC 입력 → 자동 분류(사용법문의/버그제보/기능요청/불만/칭찬/기타)
- 사용법 문의는 메뉴얼(`manual/`)에 근거한 답변 + 출처 표기
- 버그·기능요청·중대 불만은 담당자 에스컬레이션 → 대시보드에서 관리
- LLM-as-a-Judge 비동기 채점(3축 점수·재료부족/과정오류 원인)

## 아키텍처

- **백엔드**: FastAPI + LangGraph (조건부 파이프라인) + SQLAlchemy + PostgreSQL
- **LLM**: OpenAI 호환 API (`.env`의 `LLM_BASE_URL`/`LLM_MODEL`로 교체 가능)
  - 채점 설정: `JUDGE_ENABLED`(기본 true)·`JUDGE_MODEL`(기본: 답변 모델과 동일)
- **프론트엔드**: Vue 3 + Vite (챗 뷰 + VOC 대시보드)
- **메뉴얼**: `manual/*.md` — 임베딩 없는 간단 검색, 근거 없으면 답변하지 않음

## 빠른 시작

```bash
# 1. DB 기동
docker compose up -d postgres

# 2. 백엔드
cp .env.example .env        # LLM_API_KEY 입력
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 프론트엔드
cd frontend && npm install && npm run dev   # http://localhost:5173
```

## 테스트

```bash
pytest -q                        # 백엔드 전체 (LLM 불필요 — FakeProvider)
python scripts/lint_manual.py    # 메뉴얼 구조 린트
cd frontend && npm test          # 프론트엔드
python scripts/e2e_check.py      # E2E (실제 LLM, .env 필요)
```

## 관련 문서

- 아키텍처 상세: `docs/ARCHITECTURE.md` (디렉터리 구성, 그래프·채점·관측, 하네스, 테스트 전략)
- 설계: `docs/superpowers/specs/2026-08-18-doit-voc-agent-design.md`
- 구현 계획: `docs/superpowers/plans/2026-08-18-doit-voc-agent-mvp.md`
- 대상 앱: `~/git/doit` (티켓 칸반 보드)
