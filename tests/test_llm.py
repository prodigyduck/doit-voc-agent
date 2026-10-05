"""pydantic-ai 모델 팩토리 + FakeModel 테스트."""
from pydantic_ai.models.openai import OpenAIChatModel

from backend.config import Settings
from backend.llm import get_model
from tests.fakes import FakeModel


def test_get_model_api_key_있으면_모델_생성():
    s = Settings()
    s.llm_provider = "openai_compat"
    s.llm_api_key = "k"
    s.llm_base_url = "http://x"
    s.llm_model = "m"
    model = get_model(s)
    assert isinstance(model, OpenAIChatModel)


def test_get_model_api_key_없으면_None():
    s = Settings()
    s.llm_provider = "openai_compat"
    s.llm_api_key = ""
    assert get_model(s) is None


def test_get_model_이름_오버라이드():
    s = Settings()
    s.llm_provider = "openai_compat"
    s.llm_api_key = "k"
    s.llm_base_url = "http://x"
    s.llm_model = "m"
    assert get_model(s, model="judge-m") is not None


def test_fake_model_텍스트_순서대로_반환():
    from pydantic_ai import Agent

    fake = FakeModel(["a", "b"])
    agent = Agent(fake.model)
    assert agent.run_sync("x").output == "a"
    assert agent.run_sync("y").output == "b"
    assert fake.calls == ["x", "y"]


def test_fake_model_dict는_구조화_출력():
    from typing import Literal

    from pydantic import BaseModel

    from pydantic_ai import Agent

    class C(BaseModel):
        category: Literal["버그제보", "기타"]
        priority: Literal["low", "high"]

    fake = FakeModel([{"category": "버그제보", "priority": "high"}])
    result = Agent(fake.model, output_type=C).run_sync("voc").output
    assert result.category == "버그제보"
    assert result.priority == "high"
