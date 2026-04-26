from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PromptAdapterSpec:
    name: str
    adapter_cls: type
    model: str
    source: str
    availability_fixture: str
    constructor_patch: Callable
    execute_patch: Callable
    prompt: str = "Hello. My name is Inigo Montoya."


def run_shared_offline_contract_checks(spec: PromptAdapterSpec, monkeypatch) -> None:
    spec.constructor_patch(monkeypatch)

    adapter = spec.adapter_cls(spec.model, multi_turn=True, temperature=0.0)
    assert adapter.model_name == spec.model
    assert adapter.source == spec.source
    assert str(adapter) == f"Chat with {spec.model} ({spec.source})"
    assert adapter.description() == f"Chat with {spec.model} ({spec.source})"
    assert adapter.is_available() in {True, False}

    response_text = f"{spec.name} stub reply"
    spec.execute_patch(monkeypatch, adapter, response_text)
    result = adapter.execute("first prompt")
    assert result == response_text
    assert adapter._messages == [
        {"role": "user", "content": "first prompt"},
        {"role": "assistant", "content": response_text},
    ]
    assert adapter._request_messages()[-2:] == adapter._messages

    interaction_adapter = spec.adapter_cls(spec.model, multi_turn=True, temperature=0.0)
    spec.execute_patch(monkeypatch, interaction_adapter, response_text)
    interaction_calls = {"compact": 0, "assistant_args": []}

    original_compact = interaction_adapter._compact_context_if_needed
    original_record = interaction_adapter._record_assistant_response

    def spy_compact():
        interaction_calls["compact"] += 1
        return original_compact()

    def spy_record(response):
        interaction_calls["assistant_args"].append(response)
        return original_record(response)

    monkeypatch.setattr(interaction_adapter, "_compact_context_if_needed", spy_compact)
    monkeypatch.setattr(interaction_adapter, "_record_assistant_response", spy_record)
    interaction_result = interaction_adapter.execute("interaction prompt")

    assert interaction_result == response_text
    assert interaction_calls["compact"] == 1
    assert interaction_calls["assistant_args"] == [response_text]

    single_turn_adapter = spec.adapter_cls(spec.model, multi_turn=False, temperature=0.0)
    spec.execute_patch(monkeypatch, single_turn_adapter, response_text)
    single_result = single_turn_adapter.execute("one shot")
    assert single_result == response_text
    assert single_turn_adapter._messages == []

    payload_adapter = spec.adapter_cls(spec.model, multi_turn=True, temperature=0.0)
    spec.execute_patch(monkeypatch, payload_adapter, response_text)
    execute_payload = {}

    def _wrap_transport(adapter, attr_name, bucket):
        original = getattr(adapter, attr_name)

        def wrapped(*args, **kwargs):
            payload = dict(kwargs)
            if args and "model" not in payload:
                payload["model"] = args[0]
            bucket.update(payload)
            return original(*args, **kwargs)

        monkeypatch.setattr(adapter, attr_name, wrapped)

    if hasattr(payload_adapter, "_chat_completion"):
        _wrap_transport(payload_adapter, "_chat_completion", execute_payload)
    elif hasattr(payload_adapter, "_responses_request"):
        _wrap_transport(payload_adapter, "_responses_request", execute_payload)
    else:
        _wrap_transport(payload_adapter, "_messages_create", execute_payload)

    payload_result = payload_adapter.execute("payload prompt")
    assert payload_result == response_text
    assert execute_payload.get("model")
    request_list = execute_payload.get("messages", execute_payload.get("input"))
    assert isinstance(request_list, list)
    assert len(request_list) > 0

    no_context_adapter = spec.adapter_cls(spec.model, multi_turn=True, temperature=0.0)
    spec.execute_patch(monkeypatch, no_context_adapter, response_text)
    no_context_payload = {}
    if hasattr(no_context_adapter, "_chat_completion"):
        _wrap_transport(no_context_adapter, "_chat_completion", no_context_payload)
    elif hasattr(no_context_adapter, "_responses_request"):
        _wrap_transport(no_context_adapter, "_responses_request", no_context_payload)
    else:
        _wrap_transport(no_context_adapter, "_messages_create", no_context_payload)

    no_context_result = no_context_adapter.complete_text_without_context(
        "summarize this",
        model=spec.model,
        temperature=0.0,
        max_tokens=32,
    )
    assert isinstance(no_context_result, str)
    assert no_context_result == response_text
    # Contract: this helper should not mutate the chat history.
    assert no_context_adapter._messages == []
    assert no_context_payload.get("model")
    no_context_list = no_context_payload.get("messages", no_context_payload.get("input"))
    assert isinstance(no_context_list, list)
    assert len(no_context_list) > 0


def run_shared_live_contract_checks(spec: PromptAdapterSpec, request) -> None:
    # Uses fixture skip behavior in tests/conftest.py.
    if (spec.availability_fixture):
        request.getfixturevalue(spec.availability_fixture)
    adapter = spec.adapter_cls(spec.model, temperature=0.0)

    assert adapter.model_name == spec.model
    assert adapter.source == spec.source
    assert adapter.is_available() is True

    first = adapter.execute(spec.prompt)
    second = adapter.execute("What is my first name?")
    assert isinstance(first, str) and first.strip()
    assert isinstance(second, str) and second.strip()

    no_context = adapter.complete_text_without_context(
        "Respond with the single word: ready",
        model=spec.model,
        temperature=0.0,
        max_tokens=32,
    )
    assert isinstance(no_context, str)
    assert no_context.strip()
