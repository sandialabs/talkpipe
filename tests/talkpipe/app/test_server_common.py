"""Helpers shared by chatterlang_serve and chatterlang_workbench."""

import argparse

import pytest
from pydantic import BaseModel

from talkpipe.app import server_common
from talkpipe.util.config import get_config, reset_config


def test_static_dir_is_the_packaged_assets() -> None:
    assert (server_common.STATIC_DIR / "favicon.ico").is_file()
    assert (server_common.STATIC_DIR / "workbench" / "index.html").is_file()


def test_host_port_and_load_module_args() -> None:
    parser = argparse.ArgumentParser()
    server_common.add_host_port_args(parser, default_host="127.0.0.1", default_port=1)
    server_common.add_load_module_arg(parser)
    args = parser.parse_args([])
    assert (args.host, args.port, args.load_module) == ("127.0.0.1", 1, [])
    args = parser.parse_args(
        ["-o", "0.0.0.0", "-p", "8", "--load-module", "a.py", "--load-module", "b.py"]
    )
    assert (args.host, args.port, args.load_module) == ("0.0.0.0", 8, ["a.py", "b.py"])


def test_apply_cli_constants_adds_config_values(capsys: pytest.CaptureFixture[str]):
    reset_config()
    try:
        added = server_common.apply_cli_constants(["--greeting", "hi"])
        assert added == {"greeting": "hi"}
        assert get_config()["greeting"] == "hi"
        assert "greeting" in capsys.readouterr().out
        assert server_common.apply_cli_constants([]) == {}
        assert capsys.readouterr().out == ""
    finally:
        reset_config()


def test_load_module_files_or_exit(tmp_path, capsys: pytest.CaptureFixture[str]):
    module = tmp_path / "custom_mod.py"
    module.write_text("VALUE = 1\n")
    server_common.load_module_files_or_exit([str(module)])  # must not raise
    with pytest.raises(SystemExit) as excinfo:
        server_common.load_module_files_or_exit([str(tmp_path / "missing.py")])
    assert excinfo.value.code == 1
    assert "missing.py" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", True),
        ("127.0.0.1", True),
        ("127.9.9.9", True),
        ("::1", True),
        ("0.0.0.0", False),
        ("192.168.1.5", False),
        ("example.com", False),
    ],
)
def test_is_loopback_host(host: str, expected: bool) -> None:
    assert server_common.is_loopback_host(host) is expected


def test_api_key_matches() -> None:
    assert server_common.api_key_matches("k", "k")
    assert not server_common.api_key_matches("k", "other")
    assert not server_common.api_key_matches(None, "k")
    assert not server_common.api_key_matches("k", None)
    assert not server_common.api_key_matches(None, None)


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ("| print", True),
        ("  # comment\nCONST x = 1;\n| llmPrompt", True),
        ('INPUT FROM echo[data="1"] | print', False),
        ("", False),
        ("# only a comment", False),
    ],
)
def test_is_interactive_script(script: str, expected: bool) -> None:
    assert server_common.is_interactive_script(script) is expected


def test_is_output_stream() -> None:
    assert server_common.is_output_stream(iter([1]))
    assert server_common.is_output_stream([1, 2])
    assert not server_common.is_output_stream("text")
    assert not server_common.is_output_stream(b"bytes")
    assert not server_common.is_output_stream({"a": 1})
    assert not server_common.is_output_stream(None)


def test_iter_output_text_renders_models_as_json() -> None:
    class Item(BaseModel):
        a: int

    class Plain:
        def __str__(self) -> str:
            return "plain"

    assert list(server_common.iter_output_text([Item(a=1), 2, "s", Plain()])) == [
        '{"a":1}',
        "2",
        "s",
        "plain",
    ]
