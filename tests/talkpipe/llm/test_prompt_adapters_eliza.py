from pydantic import BaseModel

from talkpipe.llm.config import getPromptAdapter, getPromptSources
from talkpipe.llm.prompt_adapters import ElizaPromptAdapter

from prompt_adapter_contract_suite import (
    PromptAdapterSpec,
    run_shared_live_contract_checks,
    run_shared_offline_contract_checks,
)


def _patch_eliza_constructor(_monkeypatch):
    # Eliza has no external dependencies; constructor patch is intentionally a no-op.
    return


def _patch_eliza_execute(monkeypatch, adapter, response_text: str):
    monkeypatch.setattr(
        adapter,
        "_messages_create",
        lambda **_kwargs: {"model": adapter.model_name, "text": response_text, "structured": None},
    )


ELIZA_SPEC = PromptAdapterSpec(
    name="eliza",
    adapter_cls=ElizaPromptAdapter,
    model="Dr. Eliza",
    source="eliza",
    availability_fixture="",
    constructor_patch=_patch_eliza_constructor,
    execute_patch=_patch_eliza_execute,
)


def test_eliza_shared_offline_contract(monkeypatch):
    run_shared_offline_contract_checks(ELIZA_SPEC, monkeypatch)


def test_eliza_shared_live_contract(request):
    run_shared_live_contract_checks(ELIZA_SPEC, request)


def test_eliza_is_registered_as_prompt_source():
    assert "eliza" in getPromptSources()
    assert getPromptAdapter("eliza") is ElizaPromptAdapter


def test_eliza_remembers_name_in_multi_turn_dialogue():
    adapter = ElizaPromptAdapter("Dr. Eliza", multi_turn=True)
    first = adapter.execute("Hi, my name is Sam.")
    reply = adapter.execute("What is my first name?")

    assert "dr. eliza" in first.lower()
    assert "sam" in reply.lower()


class ScoreShape(BaseModel):
    explanation: str
    score: int


def test_eliza_guided_score_response_is_reasonable_shape():
    adapter = ElizaPromptAdapter("Dr. Eliza", output_format=ScoreShape, multi_turn=False)
    result = adapter.execute("This response is clear, specific, and relevant.")

    assert isinstance(result, ScoreShape)
    assert 0 <= result.score <= 10
    assert len(result.explanation) > 0


def test_eliza_default_branch_has_response_variance():
    adapter = ElizaPromptAdapter("Dr. Eliza", multi_turn=True)
    prompts = [
        "I have updates from yesterday.",
        "There are several moving parts in this issue.",
        "Today felt unusually busy.",
        "I need to sort my priorities.",
    ]

    replies = [adapter.execute(prompt) for prompt in prompts]
    unique_replies = set(replies)

    assert len(unique_replies) >= 2


def test_eliza_identity_phrase_only_once_without_repeat_name_query():
    adapter = ElizaPromptAdapter("Dr. Eliza", multi_turn=True)
    replies = [
        adapter.execute("Hello there."),
        adapter.execute("I have an update."),
        adapter.execute("Things are moving slowly."),
        adapter.execute("Because this is a hard week."),
    ]

    iam_count = sum(reply.lower().count("i am dr. eliza") for reply in replies)
    assert iam_count == 1


def test_eliza_reintroduces_i_am_on_second_name_query():
    adapter = ElizaPromptAdapter("Dr. Eliza", multi_turn=True)

    first = adapter.execute("Hello.")
    name_first = adapter.execute("What is your name?")
    name_second = adapter.execute("What's your name again?")

    assert "i am dr. eliza" in first.lower()
    assert "i am dr. eliza" not in name_first.lower()
    assert "my name is dr. eliza" in name_first.lower()
    assert "i am dr. eliza" in name_second.lower()
