from backend.config import Settings
from backend.llm.factory import get_llm_provider


class _FakeClient:
    """openai client 대역 — chat.completions.create 호출 기록."""

    def __init__(self, reply: str):
        self._reply = reply
        self.calls = []

    @property
    def chat(self):
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)

                class _Msg:
                    content = outer._reply

                class _Choice:
                    message = _Msg()

                class _Resp:
                    choices = [_Choice()]

                return _Resp()

        class _Chat:
            completions = _Completions()

        return _Chat()


def test_openai_compat_generate가_클라이언트를_호출한다():
    from backend.llm.openai_compat import OpenAICompatProvider

    client = _FakeClient("안녕하세요")
    provider = OpenAICompatProvider(base_url="http://x", api_key="k", model="m", client=client)

    assert provider.generate("질문") == "안녕하세요"
    assert provider.name == "openai_compat"
    assert client.calls[0]["model"] == "m"
    assert client.calls[0]["messages"][0]["content"] == "질문"


def test_factory_api_key_있으면_provider_생성():
    s = Settings()
    s.llm_provider = "openai_compat"
    s.llm_api_key = "k"
    s.llm_base_url = "http://x"
    s.llm_model = "m"
    provider = get_llm_provider(s)
    assert provider is not None
    assert provider.name == "openai_compat"


def test_factory_api_key_없으면_None():
    s = Settings()
    s.llm_provider = "openai_compat"
    s.llm_api_key = ""
    assert get_llm_provider(s) is None


def test_fake_provider_순서대로_반환():
    from tests.fakes import FakeProvider

    provider = FakeProvider(["a", "b"])
    assert provider.generate("x") == "a"
    assert provider.generate("y") == "b"
    assert provider.calls == ["x", "y"]
