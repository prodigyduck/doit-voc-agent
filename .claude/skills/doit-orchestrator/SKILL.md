---
name: doit-orchestrator
description: doit-voc-agent 개발을 구동하는 멀티 에이전트 하네스 오케스트레이터. 기능 구현 시작/계속, 단계별 게이트 운영 시 사용.
---

# doit-voc-agent 오케스트레이터

doit-voc-agent 개발 작업을 에이전트에 위임하고 품질 게이트로 진행하는 하네스.

## 언제 사용하는가

- "구현 시작", "다음 단계 진행", "하네스로 진행" 등 명시적 요청
- 기능 추가·개선 요청을 받아 단위 작업으로 분해할 때

## 하네스 구성

- manual-writer → 메뉴얼 작성 (HOW: manual-authoring)
- backend-engineer → 그래프/API (HOW: voc-pipeline)
- frontend-engineer → 챗/대시보드 (HOW: dashboard-ui)
- qa-engineer → 품질 게이트 (모든 단계 완료 시)

## 진행 방식

1. 요청을 아래 의존 순서에 따라 단위 작업으로 분해한다
2. 의존 없는 작업은 병렬 위임한다
3. 각 작업 완료 시 qa-engineer 게이트 (pytest + lint + build) 를 통과해야 커밋
4. 게이트 실패 시 해당 에이전트에게 수정 위임 후 재검증

## 재료부족 큐 소비 (Phase 3 — 스펙 2026-08-23)

트리거: "큐 처리", "재료부족 큐 소비" 요청.

1. `python scripts/gap_report.py` 로 미처리 큐 리포트 확보 (0건이면 종료 보고)
2. manual-writer 위임 — 리포트 건별로 doit 코드 근거 수집 (HOW: manual-authoring):
   - 기능 존재 → `manual/` 적절한 문서의 `##` 섹션 추가·보강 (필요시 doit 실행·Playwright 실동작 확인)
   - 기능 부재 → `manual/05-faq.md` "제공하지 않는 기능" 항목화
3. qa-engineer 게이트 + 사용자 리뷰 통과 후 커밋
4. `python scripts/gap_resolve.py --voc-id <N ...> --status resolved|absent` 마킹, 진행 원장 기록

## 의존 그래프 (스펙 §7.2)

메뉴얼 ↔ LLM 추상화 (병렬 가능) → manual_retrieval → 그래프 → API → 프론트 → E2E
