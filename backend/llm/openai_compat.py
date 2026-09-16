"""OpenAI 호환 API 기본 구현 — LLM_BASE_URL/LLM_MODEL로 교체 (스펙 §6.3)."""
from typing import Optional

from langfuse import observe

from backend.llm.base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    """OpenAI 호환 chat.completions 호출 provider."""

    def __init__(self, base_url: str, api_key: str, model: str, client: Optional[object] = None):
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=api_key)
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return "openai_compat"

    @observe(as_type="generation", name="llm_generate")
    def generate(self, prompt: str, **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.2),
        )
        return response.choices[0].message.content
