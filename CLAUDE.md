# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때의 가이드다.

## 프로젝트 개요

doit-voc-agent는 티켓 칸반 보드 앱 **doit**(`~/git/doit`)의 사용자 VOC를 처리하는 LLM 에이전트다.
채팅으로 받은 VOC를 분류(6유형)하고, 메뉴얼(`manual/`)에 근거한 답변을 생성하거나 사람에게 에스컬레이션하며, 이력을 PostgreSQL에 저장한다.

## 개발 명령

### 백엔드 (FastAPI + LangGraph)
```bash
docker compose up -d postgres          # PostgreSQL 기동
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pytest -q                              # 전체 테스트
python scripts/lint_manual.py          # 메뉴얼 구조 린트
```

### 프론트엔드 (Vue3 + Vite)
```bash
cd frontend
npm run dev        # http://localhost:5173
npm test           # vitest
npm run build
```

### E2E
```bash
python scripts/e2e_check.py            # 실제 LLM으로 대표 VOC 6개 검증 (.env 필요)
```

## 핵심 아키텍처

- 그래프: `backend/agent.py` — classify → route(조건부) → retrieve → answer / escalate → respond → save
- 노드: `backend/nodes/` 파일당 하나, `make_*_node(provider)` 팩토리 패턴
- LLM: `backend/llm/` — `LLMProvider` ABC, OpenAI 호환 기본, `.env`로 교체
- 메뉴얼: `manual/*.md` — `##` 섹션이 검색 단위, 임베딩 없는 간단 검색(`backend/manual_retrieval.py`)
- 환각 방지: 근거 없으면 답변 생성 금지 + 에스컬레이션 (핵심 품질 속성)

## VOC 처리 하네스

**트리거:** 기능 구현/개선 요청, 단계별 진행 요청 시 `doit-orchestrator` 스킬 사용.

| 에이전트 (`.claude/agents/`) | 책임 | HOW 스킬 |
|------------------------------|------|----------|
| manual-writer | 메뉴얼 작성 | manual-authoring |
| backend-engineer | 그래프/API | voc-pipeline |
| frontend-engineer | 챗/대시보드 | dashboard-ui |
| qa-engineer | 품질 게이트 | — |

각 단계 완료 시 qa-engineer 게이트 통과 후 커밋.

## 규칙

- 로그 파일 생성 금지 (콘솔만)
- LLM 호출은 반드시 `LLMProvider` 뒤에서
- 주석/프롬프트/UI 문구는 한국어
- 커밋: conventional commits 한국어 제목

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-08-20 | 서비스 대상 앱 tika→doit 전환 (프롬프트·브랜딩·시나리오) |
| 2026-08-18 | 하네스 초기 구성 (에이전트 4 + 스킬 4) |
