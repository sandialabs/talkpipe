"""The uv wrapper: argv shapes, output parsing, streaming, and the fake uv itself."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import talkpipe_appcenter as ts
from conftest import SMALL_CATALOG, FakeUv

TOOL_LIST = """\
talkpipe-vault v1.0.0 (/home/u/.local/share/uv/tools/talkpipe-vault)
- vault-server (/home/u/.local/bin/vault-server)
- vault-tui (/home/u/.local/bin/vault-tui)
Talkpipe_Writing_Assistant v1.1.0 (/home/u/.local/share/uv/tools/talkpipe-writing-assistant)
- writing-assistant (/home/u/.local/bin/writing-assistant)
"""


def test_parse_tool_list_with_paths() -> None:
    tools = ts.parse_tool_list(TOOL_LIST)

    assert sorted(tools) == ["talkpipe-vault", "talkpipe-writing-assistant"]
    vault = tools["talkpipe-vault"]
    assert vault.version == "1.0.0"
    assert vault.env == Path("/home/u/.local/share/uv/tools/talkpipe-vault")
    assert vault.commands == {
        "vault-server": Path("/home/u/.local/bin/vault-server"),
        "vault-tui": Path("/home/u/.local/bin/vault-tui"),
    }


def test_parse_tool_list_without_paths_and_empty() -> None:
    tools = ts.parse_tool_list("aider-chat v0.86.1\n- aider\n")
    assert tools["aider-chat"].env is None
    assert tools["aider-chat"].commands == {"aider": Path("aider")}
    assert ts.parse_tool_list("No tools installed\n") == {}
    assert ts.parse_tool_list("") == {}


def test_install_argv_shapes() -> None:
    uv = ts.Uv("/bin/uv")
    catalog = ts.parse_catalog(SMALL_CATALOG)
    vault = catalog.find("vault")
    assert vault is not None

    assert uv.install_argv(vault) == [
        "/bin/uv",
        "tool",
        "install",
        "--python",
        ts.DEFAULT_PYTHON,
        "--upgrade",
        "--from",
        "talkpipe-vault",
        "talkpipe-vault",
    ]
    pinned = dataclasses.replace(
        vault, release="1.0.0", index="https://idx.example/simple/"
    )
    assert uv.install_argv(pinned)[6:] == [
        "--index",
        "https://idx.example/simple/",
        "--from",
        "talkpipe-vault==1.0.0",
        "talkpipe-vault",
    ]
    direct = dataclasses.replace(
        vault, package=ts.parse_package("talkpipe-vault @ /tmp/v.whl")
    )
    assert uv.install_argv(direct)[-3:] == ["--from", "/tmp/v.whl", "talkpipe-vault"]


def test_missing_uv_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(ts.shutil, "which", lambda name: None)

    uv = ts.Uv()

    assert uv.exe == ""
    with pytest.raises(ts.UvError, match="uv was not found"):
        uv.require()


def test_uv_env_var_wins_over_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UV", "/opt/uv")
    monkeypatch.setattr(ts.shutil, "which", lambda name: "/usr/bin/uv")
    assert ts.Uv().exe == "/opt/uv"


def test_stream_filters_package_listing_and_keeps_exit_status(fake_uv: FakeUv) -> None:
    uv = ts.Uv(str(fake_uv.exe))
    entry = ts.parse_catalog(SMALL_CATALOG).find("tool")
    assert entry is not None
    lines: list[str] = []

    code = uv.install(entry, lines.append)

    assert code == 0
    assert "Resolved 12 packages in 0.42s" in lines
    assert "Installed 1 executables: some-tool" in lines
    assert not any(line.startswith(" + ") for line in lines)
    assert uv.list_tools()["some-tool"].version == "1.2.3"
    assert (fake_uv.bin / "some-tool").exists()

    fake_uv.fail_next()
    lines.clear()
    assert uv.install(entry, lines.append) == 1
    assert any("Failed to build" in line for line in lines)


def test_fake_uv_round_trip(fake_uv: FakeUv) -> None:
    uv = ts.Uv(str(fake_uv.exe))
    assert uv.version() == "0.7.8"
    assert uv.bin_dir() == fake_uv.bin.resolve()
    assert uv.list_tools() == {}
    fake_uv.set_installed("talkpipe-vault", "1.0.0", ["vault-server", "vault-tui"])
    tools = uv.list_tools()
    assert (
        tools["talkpipe-vault"].commands["vault-server"] == fake_uv.bin / "vault-server"
    )
    assert uv.uninstall("talkpipe-vault", lambda line: None) == 0
    assert uv.list_tools() == {}
    assert fake_uv.calls()[0] == ["--version"]
