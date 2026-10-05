"""테스트용 LLM 더블 — LLM 없이 그래프 전 경로 테스트 (스펙 §8)."""
from typing import List

from backend.llm.base import LLMProvider


class FakeProvider(LLMProvider):
    """예약된 응답을 순서대로 반환. 소진되면 예외 발생."""

    def __init__(self, responses: List[str]):
        self.responses = list(responses)
        self.calls: List[str] = []

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("FakeProvider: 예약된 응답이 없음")
        return self.responses.pop(0)
