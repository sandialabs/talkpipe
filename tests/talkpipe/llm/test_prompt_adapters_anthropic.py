from talkpipe.llm.prompt_adapters import AnthropicPromptAdapter

from prompt_adapter_contract_suite import (
    PromptAdapterSpec,
    run_shared_live_contract_checks,
    run_shared_offline_contract_checks,
)


def _patch_anthropic_constructor(monkeypatch):
    class DummyMessages:
        @staticmethod
        def create(**_kwargs):
            return None

    class DummyClient:
        messages = DummyMessages()

    class DummyAnthropic:
        class Anthropic:
            def __new__(cls):
                return DummyClient()

    monkeypatch.setattr(AnthropicPromptAdapter, "_require_dependency", lambda *_args, **_kwargs: DummyAnthropic)


def _patch_anthropic_execute(monkeypatch, adapter, response_text: str):
    class TextBlock:
        text = response_text

    class DummyResponse:
        content = [TextBlock()]

    monkeypatch.setattr(adapter, "_messages_create", lambda **_kwargs: DummyResponse())


ANTHROPIC_SPEC = PromptAdapterSpec(
    name="anthropic",
    adapter_cls=AnthropicPromptAdapter,
    model="claude-3-5-haiku-latest",
    source="anthropic",
    availability_fixture="requires_anthropic",
    constructor_patch=_patch_anthropic_constructor,
    execute_patch=_patch_anthropic_execute,
)


def test_anthropic_shared_offline_contract(monkeypatch):
    run_shared_offline_contract_checks(ANTHROPIC_SPEC, monkeypatch)


def test_anthropic_shared_live_contract(request):
    run_shared_live_contract_checks(ANTHROPIC_SPEC, request)


def test_anthropic_execute_includes_summary_in_system_and_messages(monkeypatch):
    _patch_anthropic_constructor(monkeypatch)
    adapter = AnthropicPromptAdapter("claude-3-5-haiku-latest", memory_mode="summary_deterministic")
    adapter._summary_message = {"role": "system", "content": "Older summary"}
    adapter._messages = [{"role": "assistant", "content": "recent"}]
    captured = {}

    class TextBlock:
        text = "ok"

    class DummyResponse:
        content = [TextBlock()]

    def fake_messages_create(**kwargs):
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(adapter, "_compact_context_if_needed", lambda: None)
    monkeypatch.setattr(adapter, "_messages_create", fake_messages_create)
    result = adapter.execute("new prompt")

    assert result == "ok"
    assert "Conversation memory:\nOlder summary" in captured["system"]
    assert any(
        msg["role"] == "assistant" and "Conversation memory:\nOlder summary" in msg["content"]
        for msg in captured["messages"]
    )
