"""설정 기반 provider 생성 — 미설정 시 None 반환 (스펙 §4.5 우아한 열화)."""
from typing import Optional

from backend.config import Settings
from backend.llm.base import LLMProvider


def get_llm_provider(settings: Settings, model: Optional[str] = None) -> Optional[LLMProvider]:
    if settings.llm_provider == "openai_compat" and settings.llm_api_key:
        from backend.llm.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=model or settings.llm_model,
        )
    return None
