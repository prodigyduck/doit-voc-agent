"""테스트용 pydantic-ai 모델 더블 — LLM 없이 파이프라인 전 경로 테스트 (스펙 §8).

responses 항목이 str이면 텍스트 응답, dict면 구조화 출력(tool_call) 응답으로 소비된다.
예약된 응답이 소진되면 예외 발생 — 실패 경로 폴백 테스트에 그대로 쓴다.
"""
from typing import Any, List

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel


class FakeModel:
    """예약된 응답을 순서대로 반환하는 FunctionModel 래퍼."""

    def __init__(self, responses: List[Any]):
        self.responses = list(responses)
        self.calls: List[str] = []
        self.model = FunctionModel(self._fn)

    def _fn(self, messages: List[ModelMessage], info) -> ModelResponse:
        prompt = ""
        last = messages[-1]
        if getattr(last, "parts", None):
            prompt = str(last.parts[-1].content)
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("FakeModel: 예약된 응답이 없음")
        item = self.responses.pop(0)
        if isinstance(item, dict):
            return ModelResponse(
                parts=[ToolCallPart(tool_name="final_result", args=dict(item))]
            )
        return ModelResponse(parts=[TextPart(str(item))])

    @property
    def name(self) -> str:
        return "fake"
