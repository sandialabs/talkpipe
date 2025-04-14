import pytest
from typing import Iterable
import pickle
import argparse
from io import StringIO
from talkpipe.app import chatcli
from testutils import monkeypatched_talkpipe_io_prompt

@pytest.mark.online
def test_run_chat_pipeline(monkeypatch, capsys, monkeypatched_talkpipe_io_prompt, tmp_path):
    # Mock the parsed arguments
    class MockArgs:
        system_prompt = "You are a helpful and friendly assistant."
        single_turn = False
        model = None
        source = None
        outfile = str(tmp_path / "chat_output.txt")

    # Monkeypatch ArgumentParser.parse_args to return MockArgs
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: MockArgs())

    monkeypatched_talkpipe_io_prompt(["My name is bob.", "What is my name?"])

    # Run the function
    chatcli.run_chat_pipeline()

    # Capture stdout
    captured = capsys.readouterr()

    # Verify that the name "bob" appears in the output
    assert "bob" in captured.out.lower(), f"Expected 'bob' in output, but got: {captured.out}"

    # Verify that the output file was written
    with open(MockArgs.outfile, "rb") as f:
        output = pickle.load(f)
        assert isinstance(output, Iterable), f"Expected Iterable output, but got: {output}"
        assert "bob" in output[-1].lower(), f"Expected 'bob' in output file, but got: {output}"