"""pydantic-ai Agent 정의 — classify(구조화 출력)/answer/escalate/judge (스펙 §4.1).

구조화 출력: classify는 result_type=Classification으로 타입 검증이 pydantic에서 일어난다.
instrument=True는 Langfuse 등 OTel 백엔드로 스팬을 내보낸다.
"""
import threading
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model

# constants.CATEGORIES/PRIORITIES와 항상 일치시킬 것 — Literal은 값을 못 박아야 검증됨
CATEGORIES_T = Literal["사용법문의", "버그제보", "기능요청", "불만", "칭찬", "기타"]
PRIORITIES_T = Literal["low", "medium", "high"]


class Classification(BaseModel):
    """classify 구조화 출력 — 허용값 밖이면 pydantic 검증 실패로 재시도/폴백된다."""

    category: CATEGORIES_T
    priority: PRIORITIES_T


@dataclass
class AgentBundle:
    classify: Agent
    answer: Agent
    escalate: Agent
    judge: Agent


CLASSIFY_INSTRUCTIONS = """당신은 칸반 보드 앱 'doit'의 VOC(고객 소리) 분류 전문가입니다.

사용자 VOC를 다음 기준으로 분류합니다.

[유형 (category)]
- 사용법문의: 앱 사용법이나 기능에 대한 질문. 문장이 질문형("어떻게 하나요?")이 아니어도,
  기능을 찾지 못해 헤매거나 기대한 화면이 안 보인다는 표현("목록에서 안 보여요", "어디 있는지 모르겠어요")은
  안내로 해결할 수 있으므로 이 유형입니다.
- 버그제보: 오류 메시지, 비정상 종료, 저장 실패, 데이터 손실 등 앱 자체가 잘못 동작하는 증상 보고.
  조작 방법을 몰라 생긴 일이 아니라 앱이 고장났다는 보고일 때 이 유형입니다.
- 기능요청: 새 기능이나 개선 요청
- 불만: 불만족스러운 감정 표현
- 칭찬: 칭찬, 긍정 피드백
- 기타: 어느 유형에도 속하지 않음

[유형 판정 예시]
- "완료한 티켓이 보드에서 사라졌어요" → 사용법문의 (완료 티켓 숨김 규칙 안내로 해결)
- "완료한 티켓이 보드에서 사라졌어요. 어디서 확인하나요?" → 사용법문의
- "티켓이 저장되지 않아요" → 버그제보 (저장 실패는 실제 오동작)
- "앱을 켜면 바로 꺼집니다" → 버그제보 (비정상 종료)

[우선순위 (priority)]
- high: 데이터 손실, 앱 사용 불가, 매우 심각한 불만
- medium: 기능 요청, 일반적인 불만, 판단이 애매한 경우
- low: 단순 질문, 칭찬, 가벼운 의견"""

ANSWER_INSTRUCTIONS = """당신은 칸반 보드 앱 'doit'의 고객 지원 담당자입니다.

[사용자 VOC]와 [메뉴얼 근거]를 함께 받아 답변합니다.
- 근거에 있는 내용만 사용해서 답변하세요.
- 근거에 없는 내용을 절대 지어내지 마세요.
- 근거가 일부만 있으면 있는 내용만 안내하세요.
- 친절하고 간결한 한국어로 작성하고, 절차가 있으면 번호 목록을 사용하세요.
- 답변 마지막 줄에 아래 형식으로 출처를 모두 나열하세요.
📖 출처: 파일명#섹션제목"""

ESCALATE_INSTRUCTIONS = """당신은 칸반 보드 앱 'doit'의 고객 지원 담당자입니다.
사용자 VOC는 사람이 확인해야 하는 유형입니다.
사용자에게 전달할 접수 완료 안내 문구를 2~3문장의 친절한 한국어로 작성하세요.
해결 방법이나 일정을 지어내지 말고, 접수되었음과 검토하겠다는 점만 안내하세요."""

JUDGE_INSTRUCTIONS = """당신은 칸반 보드 앱 'doit' 고객지원 답변의 품질 채점자입니다.

[원본 VOC], [생성된 답변], [참조한 메뉴얼 출처]를 보고 답변을 채점합니다.

[축 (각 1~5 정수)]
- completeness(완결성): VOC 질문에 답변이 충분한가. 질문이 요구하는 해결책이 출처에 없어 안내만 한 답변은 질문을 해결하지 못했으므로 반드시 감점한다
- accuracy(정확성): 출처와 일치하는가. 출처에 없는 내용을 서술(환각)하면 1점
- fluency(유창성): 문장이 자연스럽고 고객 응대 톤에 적합한가

[감점 축이 있을 때 원인 (cause)]
- 재료부족: 출처에 필요한 정보가 없어 답변이 불완전. 해결책이 출처에 없다는 정직한 부정 안내(예: "메뉴얼에 없음")도 이 원인으로 판정
- 과정오류: 출처에 정보가 있는데 답변이 놓치거나 잘못 인용·문장이 깨짐
- 해당없음: 감점 축 없음"""

JUDGE_OUTPUT_FORMAT = """아래 JSON 형식만 출력하세요. 다른 설명은 금지합니다.
{"completeness": 4, "accuracy": 5, "fluency": 5, "cause": "재료부족|과정오류|해당없음", "reason": "감점 근거 한 줄"}"""

_agents_cache: Dict[int, AgentBundle] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 8


def build_agents(model: Model) -> AgentBundle:
    """모델 하나에 대한 Agent 묶음 — id(model)로 캐시하여 요청마다 재생성하지 않는다."""
    with _cache_lock:
        cached = _agents_cache.get(id(model))
        if cached is not None:
            return cached
        bundle = AgentBundle(
            classify=Agent(
                model,
                output_type=Classification,
                instructions=CLASSIFY_INSTRUCTIONS,
                instrument=True,
                retries=1,
            ),
            answer=Agent(model, output_type=str, instructions=ANSWER_INSTRUCTIONS, instrument=True),
            escalate=Agent(model, output_type=str, instructions=ESCALATE_INSTRUCTIONS, instrument=True),
            judge=Agent(model, output_type=str, instructions=JUDGE_INSTRUCTIONS, instrument=True),
        )
        if len(_agents_cache) >= _CACHE_MAX:
            _agents_cache.clear()
        _agents_cache[id(model)] = bundle
        return bundle


def classification_to_dict(result: Classification) -> Dict[str, str]:
    return {"category": result.category, "priority": result.priority}
