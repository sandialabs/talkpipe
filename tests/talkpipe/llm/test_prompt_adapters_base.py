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
        adapter._require_dependency(
            "missing_module_for_talkpipe_tests", "Missing", "fake-extra"
        )


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


def test_require_dependency_distinguishes_missing_from_broken(monkeypatch):
    adapter = DummyPromptAdapter()

    # a real, importable module comes back as-is
    assert adapter._require_dependency("json", "JSON", "json").__name__ == "json"

    # missing package -> points at the extra
    with pytest.raises(ImportError, match=r"talkpipe\[nope\]"):
        adapter._require_dependency("definitely_not_a_module_xyz", "Nope", "nope")

    # package present but a *transitive* import fails -> "installed but failed"
    import builtins

    real_import = builtins.__import__

    def broken(name, *args, **kwargs):
        if name == "brokenpkg":
            raise ModuleNotFoundError(
                "No module named 'its_dependency'", name="its_dependency"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    with pytest.raises(ImportError, match="installed but failed to import"):
        adapter._require_dependency("brokenpkg", "Broken", "broken")

    def broken_generic(name, *args, **kwargs):
        if name == "brokenpkg2":
            raise ImportError("dll load failed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_generic)
    with pytest.raises(ImportError, match="dll load failed"):
        adapter._require_dependency("brokenpkg2", "Broken", "broken")


def test_format_message_for_debug_redacts_images_and_truncates():
    adapter = DummyPromptAdapter()

    long = "x" * 600
    plain = adapter._format_message_for_debug({"role": "user", "content": long})
    assert plain["role"] == "user"
    assert plain["content"].endswith("...[truncated]")
    assert len(plain["content"]) == 500 + len("...[truncated]")

    with_images = adapter._format_message_for_debug(
        {"role": "user", "content": long, "images": ["QUJD", "REVGRw=="]}
    )
    assert with_images["images"] == ["<4 base64 chars>", "<8 base64 chars>"]
    assert with_images["content"].endswith("...[truncated]")

    parts = adapter._format_message_for_debug(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
                {"type": "image", "source": {"data": "..."}},
                "loose string part",
            ],
        }
    )
    assert parts["content"] == [
        {"type": "text", "text": "hi"},
        {"type": "image_url", "image": "<redacted>"},
        {"type": "image", "image": "<redacted>"},
        "loose string part",
    ]


def test_execute_turn_is_not_supported_by_default():
    from talkpipe.llm.content import TextPart, UserTurn

    adapter = DummyPromptAdapter()
    with pytest.raises(NotImplementedError, match="DummyPromptAdapter"):
        adapter.execute_turn(UserTurn(parts=[TextPart(text="hello")]))
