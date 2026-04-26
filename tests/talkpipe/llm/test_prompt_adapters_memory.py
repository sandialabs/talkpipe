import pytest

from talkpipe.llm.prompt_adapter_base import AbstractLLMPromptAdapter


class DummyMemoryAdapter(AbstractLLMPromptAdapter):
    def __init__(self, model="dummy-model", **kwargs):
        super().__init__(model=model, source="dummy", **kwargs)
        self.no_context_response = "llm summary response"

    def execute(self, prompt: str) -> str:
        return prompt

    def is_available(self) -> bool:
        return True

    def complete_text_without_context(self, prompt: str, *, model=None, temperature=0.0, max_tokens=None) -> str:
        return self.no_context_response


def test_configure_memory_mode_sets_expected_strategy_and_mode():
    adapter = DummyMemoryAdapter(memory_mode="summary_truncate")
    assert adapter._memory_mode == "summary_truncate"
    assert adapter._summarization_mode == "rolling"
    assert adapter._summary_strategy == "truncate"

    adapter._configure_memory_mode("summary_deterministic")
    assert adapter._memory_mode == "summary_deterministic"
    assert adapter._summary_strategy == "deterministic"

    adapter._configure_memory_mode("full")
    assert adapter._summarization_mode == "off"


def test_configure_memory_mode_rejects_unknown_mode():
    adapter = DummyMemoryAdapter()
    with pytest.raises(ValueError, match="Unknown memory_mode"):
        adapter._configure_memory_mode("not-a-real-mode")


def test_effective_context_token_trigger_accepts_only_absolute_values():
    adapter = DummyMemoryAdapter(context_token_trigger=None)
    assert adapter._get_effective_context_token_trigger() is None

    adapter._context_token_trigger = 0.9
    assert adapter._get_effective_context_token_trigger() is None

    adapter._context_token_trigger = 4000
    assert adapter._get_effective_context_token_trigger() == 4000


def test_estimate_tokens_and_needs_compaction_threshold():
    adapter = DummyMemoryAdapter(memory_mode="summary_truncate", context_token_trigger=10, system_prompt=None)
    adapter._messages = [{"role": "user", "content": "abcdefghij"}]
    assert adapter._estimate_tokens(adapter._request_messages()) == 8
    assert adapter._needs_compaction() is False

    adapter._messages.append({"role": "assistant", "content": "abcdefghijklmnop"})
    assert adapter._needs_compaction() is True


def test_needs_compaction_returns_false_when_not_rolling_or_no_budget():
    full_mode = DummyMemoryAdapter(memory_mode="full", context_token_trigger=1, system_prompt=None)
    full_mode._messages = [{"role": "user", "content": "x" * 100}]
    assert full_mode._needs_compaction() is False

    rolling_no_budget = DummyMemoryAdapter(memory_mode="summary_truncate", context_token_trigger=None, system_prompt=None)
    rolling_no_budget._messages = [{"role": "user", "content": "x" * 100}]
    assert rolling_no_budget._needs_compaction() is False


def test_messages_to_summary_text_and_prompt_builder_include_expected_sections():
    adapter = DummyMemoryAdapter()
    archived = [
        {"role": "user", "content": "Remember this"},
        {"role": "assistant", "content": "I will"},
    ]
    text = adapter._messages_to_summary_text(archived)
    assert text == "USER: Remember this\nASSISTANT: I will"

    prompt = adapter._build_summary_prompt("old summary", archived)
    assert "Previous summary:\nold summary" in prompt
    assert "Archived messages:\nUSER: Remember this" in prompt


def test_summarize_truncate_respects_character_limit():
    adapter = DummyMemoryAdapter(memory_mode="summary_truncate")
    adapter._summary_max_chars = 10
    summary = adapter._summarize_truncate("", [{"role": "user", "content": "123456789012345"}])
    assert summary == "6789012345"


def test_summarize_deterministic_and_truncate_return_empty_for_blank_input():
    adapter = DummyMemoryAdapter()
    assert adapter._summarize_deterministic("", []) == ""
    assert adapter._summarize_truncate("", []) == ""


def test_summarize_history_uses_llm_then_clips_to_max_chars():
    adapter = DummyMemoryAdapter(memory_mode="summary_llm")
    adapter._summary_max_chars = 5
    adapter.no_context_response = "abcdefghijk"
    summary = adapter._summarize_history("", [{"role": "user", "content": "hi"}])
    assert summary == "abcde"


def test_summarize_history_falls_back_to_deterministic_when_llm_fails(monkeypatch):
    adapter = DummyMemoryAdapter(memory_mode="summary_llm")

    def raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(adapter, "_summarize_with_llm", raise_runtime_error)
    summary = adapter._summarize_history("", [{"role": "user", "content": "capture this fact"}])
    assert "deterministic fallback" in summary.lower()


def test_summarize_history_propagates_not_implemented(monkeypatch):
    adapter = DummyMemoryAdapter(memory_mode="summary_llm")

    def raise_not_implemented(*_args, **_kwargs):
        raise NotImplementedError("missing override")

    monkeypatch.setattr(adapter, "_summarize_with_llm", raise_not_implemented)
    with pytest.raises(NotImplementedError):
        adapter._summarize_history("", [{"role": "user", "content": "x"}])


def test_summarize_history_falls_back_to_truncate_when_deterministic_is_empty(monkeypatch):
    adapter = DummyMemoryAdapter(memory_mode="summary_llm")

    def raise_runtime_error(*_args, **_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(adapter, "_summarize_with_llm", raise_runtime_error)
    monkeypatch.setattr(adapter, "_summarize_deterministic", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(adapter, "_summarize_truncate", lambda *_args, **_kwargs: "truncate fallback")

    assert adapter._summarize_history("", [{"role": "user", "content": "x"}]) == "truncate fallback"


def test_summarize_history_direct_deterministic_and_truncate_paths():
    deterministic = DummyMemoryAdapter(memory_mode="summary_deterministic")
    deterministic_summary = deterministic._summarize_history("", [{"role": "user", "content": "fact"}])
    assert "deterministic fallback" in deterministic_summary.lower()

    truncate = DummyMemoryAdapter(memory_mode="summary_truncate")
    truncate._summary_max_chars = 6
    truncate_summary = truncate._summarize_history("", [{"role": "user", "content": "123456789"}])
    assert truncate_summary == "456789"


def test_compact_context_recent_only_drops_archived_messages_without_summary():
    adapter = DummyMemoryAdapter(
        memory_mode="recent_only",
        context_token_trigger=1,
        unsummarized_message_count=1,
        system_prompt=None,
    )
    adapter._messages = [
        {"role": "user", "content": "older"},
        {"role": "assistant", "content": "keep me"},
    ]
    adapter._compact_context_if_needed()
    assert adapter._summary_message is None
    assert adapter._messages == [{"role": "assistant", "content": "keep me"}]


def test_compact_context_returns_early_when_not_needed():
    adapter = DummyMemoryAdapter(memory_mode="summary_truncate", context_token_trigger=9999, system_prompt=None)
    adapter._messages = [{"role": "user", "content": "small"}]
    adapter._compact_context_if_needed()
    assert adapter._messages == [{"role": "user", "content": "small"}]
    assert adapter._summary_message is None


def test_compact_context_skips_when_message_count_not_above_keep_count():
    adapter = DummyMemoryAdapter(
        memory_mode="summary_truncate",
        context_token_trigger=1,
        unsummarized_message_count=3,
        system_prompt=None,
    )
    adapter._messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    ]
    adapter._compact_context_if_needed()
    assert adapter._messages == [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    ]
    assert adapter._summary_message is None


def test_compact_context_creates_summary_and_keeps_recent_messages():
    adapter = DummyMemoryAdapter(
        memory_mode="summary_truncate",
        context_token_trigger=1,
        unsummarized_message_count=1,
        system_prompt=None,
    )
    adapter._summary_max_chars = 50
    adapter._messages = [
        {"role": "user", "content": "older message one"},
        {"role": "assistant", "content": "newest stays"},
    ]
    adapter._compact_context_if_needed()
    assert adapter._summary_message is not None
    assert adapter._summary_message["role"] == "system"
    assert "older message one" in adapter._summary_message["content"]
    assert adapter._messages == [{"role": "assistant", "content": "newest stays"}]


def test_compact_context_debug_mode_logs_archived_and_recent_payloads(monkeypatch):
    adapter = DummyMemoryAdapter(
        memory_mode="summary_truncate",
        context_token_trigger=1,
        unsummarized_message_count=1,
        system_prompt=None,
        debug_messages=True,
    )
    adapter._messages = [
        {"role": "user", "content": "older"},
        {"role": "assistant", "content": "recent"},
    ]
    calls = []

    def capture_payload(name, messages):
        calls.append((name, list(messages)))

    monkeypatch.setattr(adapter, "_log_message_payload", capture_payload)
    adapter._compact_context_if_needed()

    payload_names = [name for name, _ in calls]
    assert payload_names == ["archived_messages", "recent_messages"]
