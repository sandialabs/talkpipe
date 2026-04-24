from talkpipe.data.text import englishnormalize as en


def test_englishnormalize_normalize_text():
    assert en.normalize_text("  Hello,\n  World!  ") == "hello, world!"


def test_englishnormalize_summarize_iterable_deterministic():
    lines = [
        "My name is Bob.",
        "I live in Boston.",
        "Please answer briefly.",
        "What is the next step?",
    ]
    summary = en.summarize(lines, max_chars=200)
    assert isinstance(summary, str)
    assert "Constraints:" in summary
    assert "Key facts:" in summary
    assert "Open items:" in summary
    assert len(summary) <= 200


def test_englishnormalize_summarize_repeatable():
    lines = ["My name is Bob.", "Please use bullet points.", "What is next?"]
    s1 = en.summarize(lines, max_chars=180)
    s2 = en.summarize(lines, max_chars=180)
    assert s1 == s2


def test_englishnormalize_summarize_prefers_constraints_when_bounded():
    lines = [
        "USER: The sky is blue.",
        "ASSISTANT: Nice to meet you.",
        "USER: Please keep responses short.",
        "USER: Use bullet points.",
        "ASSISTANT: Sure, I can do that.",
    ]
    summary = en.summarize(lines, max_chars=120)
    assert "Please keep responses short." in summary or "Use bullet points." in summary


def test_englishnormalize_summarize_prefers_recent_facts():
    lines = [
        "USER: My name is OldName.",
        "ASSISTANT: Acknowledged.",
        "USER: My name is NewName.",
    ]
    summary = en.summarize(lines, max_chars=220)
    old_idx = summary.find("My name is OldName.")
    new_idx = summary.find("My name is NewName.")
    assert "My name is NewName." in summary
    assert old_idx != -1, f"Expected old fact in summary, got: {summary}"
    assert new_idx != -1, f"Expected new fact in summary, got: {summary}"
    assert new_idx < old_idx, f"Expected newer fact before older fact, got: {summary}"
