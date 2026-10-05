"""pydantic-ai 모델 팩토리 — 모든 LLM 호출의 유일한 진입점 (스펙 §6.3).

LLM 교체는 .env의 LLM_BASE_URL/LLM_MODEL로 한다 (OpenAI 호환).
"""
from typing import Optional

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import Settings

__all__ = ["get_model"]


def get_model(settings: Settings, model: Optional[str] = None) -> Optional[Model]:
    """설정 기반 pydantic-ai 모델 생성 — 미설정 시 None (스펙 §4.5 우아한 열화)."""
    if settings.llm_provider == "openai_compat" and settings.llm_api_key:
        return OpenAIChatModel(
            model or settings.llm_model,
            provider=OpenAIProvider(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
            ),
        )
    return None
