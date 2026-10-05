"""LLM Provider 추상 베이스 — provider 교체 가능 추상화 (스펙 §6.3).

모든 LLM provider는 이 인터페이스를 구현해야 한다.
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """LLM provider 추상 인터페이스."""

    @property
    @abstractmethod
    def name(self) -> str:
        """provider 이름 (예: 'openai_compat')"""
        raise NotImplementedError

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """프롬프트를 받아 LLM 응답을 생성 (동기).

        Args:
            prompt: 입력 프롬프트
            **kwargs: provider별 추가 옵션 (temperature 등)
        Returns:
            생성된 텍스트 응답
        """
        raise NotImplementedError
