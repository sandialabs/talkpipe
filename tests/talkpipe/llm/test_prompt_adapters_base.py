import pytest

from talkpipe.llm.prompt_adapter_base import AbstractLLMPromptAdapter


class DummyPromptAdapter(AbstractLLMPromptAdapter):
    def __init__(self, model="dummy-model", **kwargs):
        super().__init__(model=model, source="dummy", **kwargs)

    def execute(self, prompt: str) -> str:
        self._messages.append({"role": "user", "content": prompt})
        response = f"echo:{prompt}"
        self._record_assistant_response(response)
        return response

    def is_available(self) -> bool:
        return True


def test_request_messages_includes_prefix_summary_and_live_messages():
    adapter = DummyPromptAdapter(system_prompt="System prompt")
    adapter._summary_message = {"role": "system", "content": "Summary prompt"}
    adapter._messages = [{"role": "user", "content": "hello"}]

    assert adapter._request_messages() == [
        {"role": "system", "content": "System prompt"},
        {"role": "system", "content": "Summary prompt"},
        {"role": "user", "content": "hello"},
    ]


def test_apply_temperature_if_explicit_only_sets_when_provided():
    explicit = DummyPromptAdapter(temperature=0.2)
    implicit = DummyPromptAdapter()
    explicit_params = {}
    implicit_params = {}

    explicit._apply_temperature_if_explicit(explicit_params)
    implicit._apply_temperature_if_explicit(implicit_params)

    assert explicit_params == {"temperature": 0.2}
    assert implicit_params == {}


def test_record_assistant_response_respects_multi_turn_setting():
    multi_turn_adapter = DummyPromptAdapter(multi_turn=True)
    single_turn_adapter = DummyPromptAdapter(multi_turn=False)

    multi_turn_adapter._record_assistant_response("saved")
    single_turn_adapter._messages = [{"role": "user", "content": "existing"}]
    single_turn_adapter._record_assistant_response("cleared")

    assert multi_turn_adapter._messages == [{"role": "assistant", "content": "saved"}]
    assert single_turn_adapter._messages == []


def test_record_assistant_response_clears_summary_when_single_turn():
    adapter = DummyPromptAdapter(multi_turn=False)
    adapter._summary_message = {"role": "system", "content": "old summary"}

    adapter._record_assistant_response("reply")

    assert adapter._messages == []
    assert adapter._summary_message is None


def test_require_dependency_raises_helpful_error_for_missing_package():
    adapter = DummyPromptAdapter()
    module = adapter._require_dependency("json", "JSON", "json")
    assert module is not None

    with pytest.raises(ImportError, match=r"pip install talkpipe\[fake-extra\]"):
        adapter._require_dependency("missing_module_for_talkpipe_tests", "Missing", "fake-extra")


def test_complete_text_without_context_default_raises_not_implemented():
    adapter = DummyPromptAdapter()
    with pytest.raises(NotImplementedError, match="complete_text_without_context"):
        adapter.complete_text_without_context("summarize me")


def test_description_string_and_repr():
    adapter = DummyPromptAdapter(model="demo-model")
    expected = "Chat with demo-model (dummy)"
    assert adapter.description() == expected
    assert str(adapter) == expected
    assert repr(adapter) == expected


def test_source_property_returns_configured_source():
    adapter = DummyPromptAdapter()
    assert adapter.source == "dummy"


def test_role_map_overrides_system_and_populates_prefix_messages():
    adapter = DummyPromptAdapter(
        system_prompt="Default system",
        role_map="system:Role map system,user:First user,assistant:First assistant",
    )
    assert adapter._system_message == {"role": "system", "content": "Role map system"}
    assert adapter._prefix_messages == [
        {"role": "system", "content": "Role map system"},
        {"role": "user", "content": "First user"},
        {"role": "assistant", "content": "First assistant"},
    ]


def test_role_map_without_system_uses_system_prompt_prefix_first():
    adapter = DummyPromptAdapter(
        system_prompt="Default system",
        role_map="user:First user,assistant:First assistant",
    )
    assert adapter._system_message == {"role": "system", "content": "Default system"}
    assert adapter._prefix_messages == [
        {"role": "system", "content": "Default system"},
        {"role": "user", "content": "First user"},
        {"role": "assistant", "content": "First assistant"},
    ]


def test_log_message_payload_debug_mode_sanitizes_and_logs(monkeypatch):
    adapter = DummyPromptAdapter(debug_messages=True)
    captured = {}

    def fake_debug(message, *args):
        captured["message"] = message
        captured["args"] = args

    monkeypatch.setattr("talkpipe.llm.prompt_adapter_base.logger.debug", fake_debug)
    adapter._log_message_payload(
        "messages",
        [{"role": "user", "content": "x" * 510}],
    )

    assert "LLM outbound payload" in captured["message"]
    payload_json = captured["args"][-1]
    assert "...[truncated]" in payload_json


def test_log_message_payload_noop_when_debug_disabled(monkeypatch):
    adapter = DummyPromptAdapter(debug_messages=False)
    captured = {"calls": 0}

    def fake_debug(*_args, **_kwargs):
        captured["calls"] += 1

    monkeypatch.setattr("talkpipe.llm.prompt_adapter_base.logger.debug", fake_debug)
    adapter._log_message_payload("messages", [{"role": "user", "content": "hello"}])
    assert captured["calls"] == 0


def test_clip_debug_text_handles_none_short_and_long_text():
    adapter = DummyPromptAdapter()

    assert adapter._clip_debug_text(None) == ""
    assert adapter._clip_debug_text("short", limit=10) == "short"
    assert adapter._clip_debug_text("abcdefgh", limit=5) == "abcde...[truncated]"
