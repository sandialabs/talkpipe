from talkpipe.llm.prompt_adapters import OpenAIPromptAdapter

from prompt_adapter_contract_suite import (
    PromptAdapterSpec,
    run_shared_live_contract_checks,
    run_shared_offline_contract_checks,
)


def _patch_openai_constructor(monkeypatch):
    class DummyResponses:
        @staticmethod
        def parse(**_kwargs):
            return None

        @staticmethod
        def create(**_kwargs):
            return None

    class DummyClient:
        responses = DummyResponses()

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    return None

    class DummyOpenAI:
        NOT_GIVEN = object()

        class OpenAI:
            def __new__(cls):
                return DummyClient()

    monkeypatch.setattr(OpenAIPromptAdapter, "_require_dependency", lambda *_args, **_kwargs: DummyOpenAI)


def _patch_openai_execute(monkeypatch, adapter, response_text: str):
    class DummyResponse:
        output_text = response_text
        output_parsed = None

    monkeypatch.setattr(adapter, "_responses_request", lambda **_kwargs: DummyResponse())


OPENAI_SPEC = PromptAdapterSpec(
    name="openai",
    adapter_cls=OpenAIPromptAdapter,
    model="gpt-4.1-nano",
    source="openai",
    availability_fixture="requires_openai",
    constructor_patch=_patch_openai_constructor,
    execute_patch=_patch_openai_execute,
)


def test_openai_shared_offline_contract(monkeypatch):
    run_shared_offline_contract_checks(OPENAI_SPEC, monkeypatch)


def test_openai_shared_live_contract(request):
    run_shared_live_contract_checks(OPENAI_SPEC, request)


def test_openai_availability_probe_caps_generation(monkeypatch):
    # Same contract as the ollama adapter: the availability probe must cap the
    # test completion instead of paying for a full uncapped generation.
    _patch_openai_constructor(monkeypatch)
    adapter = OpenAIPromptAdapter("gpt-4.1-nano")
    seen = {}

    class DummyCompletions:
        @staticmethod
        def create(**kwargs):
            seen.update(kwargs)
            return object()

    class DummyChat:
        completions = DummyCompletions()

    class DummyClient:
        chat = DummyChat()

    adapter.client = DummyClient()
    assert adapter.is_available() is True
    assert seen.get("max_completion_tokens") == 1


def test_openai_responses_request_switches_between_parse_and_create(monkeypatch):
    _patch_openai_constructor(monkeypatch)
    adapter = OpenAIPromptAdapter("gpt-4.1-nano")

    calls = {"parse": 0, "create": 0}

    class DummyResponses:
        @staticmethod
        def parse(**_kwargs):
            calls["parse"] += 1
            return object()

        @staticmethod
        def create(**_kwargs):
            calls["create"] += 1
            return object()

    class DummyClient:
        responses = DummyResponses()

    adapter.client = DummyClient()
    adapter._responses_request(parse=True, model="m", input=[])
    adapter._responses_request(parse=False, model="m", input=[])

    assert calls == {"parse": 1, "create": 1}
