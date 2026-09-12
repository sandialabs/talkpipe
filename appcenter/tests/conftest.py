"""Shared fixtures: a fake ``uv`` on PATH, a fake PyPI, and an isolated home.

The real uv is never run by the test suite. ``fake_uv`` writes an executable
``uv`` into a temporary directory that records every argv it receives,
answers the handful of commands the App Center uses in the exact output format of
real uv, and keeps its "installed tools" in a JSON file the tests can read
and pre-seed.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import talkpipe_appcenter as ts

FAKE_UV_SCRIPT = r'''#!@@PYTHON@@
"""A stand-in for uv that records argv and mimics the outputs the App Center parses."""
import json, os, sys
from pathlib import Path

ROOT = Path(@@ROOT@@)
STATE = ROOT / "uv-state.json"
CALLS = ROOT / "uv-calls.jsonl"


def load():
    return json.loads(STATE.read_text())


def save(state):
    STATE.write_text(json.dumps(state, indent=1))


def main(argv):
    with CALLS.open("a") as fh:
        fh.write(json.dumps(argv) + "\n")
    state = load()
    bin_dir = Path(state["bin"])
    tools_dir = Path(state["tools_dir"])
    if argv == ["--version"]:
        print("uv 0.7.8")
        return 0
    if argv == ["tool", "dir", "--bin"]:
        print(bin_dir)
        return 0
    if argv == ["tool", "list", "--show-paths"]:
        if not state["tools"]:
            print("No tools installed", file=sys.stderr)
            return 0
        for name, tool in state["tools"].items():
            print(f"{name} v{tool['version']} ({tools_dir / name})")
            for cmd in tool["commands"]:
                print(f"- {cmd} ({bin_dir / cmd})")
        return 0
    if argv[:2] == ["tool", "install"]:
        name = argv[-1]
        spec = argv[argv.index("--from") + 1]
        if state.get("fail_next"):
            state["fail_next"] = False
            save(state)
            print("Resolved 3 packages in 0.10s")
            print(f"error: Failed to build `{name}`", file=sys.stderr)
            return 1
        # Real uv only considers pre-releases when asked; without the flag it
        # resolves to the newest release, which is what makes a plain upgrade
        # able to move an installed pre-release backwards.
        pre_ok = "--prerelease" in argv and argv[argv.index("--prerelease") + 1] == "allow"
        if "==" in spec:
            version = spec.split("==", 1)[1]
        elif pre_ok and name in state.get("latest_pre", {}):
            version = state["latest_pre"][name]
        else:
            version = state.get("latest", {}).get(name, "1.2.3")
        commands = state.get("canned_commands", {}).get(name, [name])
        icon = state.get("icons", {}).get(name)
        print("Resolved 12 packages in 0.42s")
        print("Prepared 12 packages in 1.00s")
        print("Installed 12 packages in 30ms")
        print(f" + {name}=={version}")
        print(" + somedep==0.1.0")
        print(f"Installed {len(commands)} executables: " + ", ".join(commands))
        bin_dir.mkdir(parents=True, exist_ok=True)
        for cmd in commands:
            stub = bin_dir / cmd
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        env = tools_dir / name
        site = env / "lib" / "python3.12" / "site-packages"
        site.mkdir(parents=True, exist_ok=True)
        if icon:
            (site / icon).parent.mkdir(parents=True, exist_ok=True)
            (site / icon).write_bytes(b"\x89PNG fake")
        state["tools"][name] = {"version": version, "commands": commands}
        save(state)
        return 0
    if argv[:2] == ["tool", "uninstall"]:
        name = argv[2]
        tool = state["tools"].pop(name, None)
        if tool is None:
            print(f"`{name}` is not installed", file=sys.stderr)
            return 1
        for cmd in tool["commands"]:
            (bin_dir / cmd).unlink(missing_ok=True)
        save(state)
        print(f"Uninstalled {len(tool['commands'])} executables: " + ", ".join(tool["commands"]))
        return 0
    if argv == ["tool", "update-shell"]:
        return 0
    print(f"unexpected argv: {argv}", file=sys.stderr)
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


class FakeUv:
    """Handle on the fake uv: its recorded calls and its editable state."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.exe = root / "bin" / "uv"
        self.bin = root / "bin"
        self.tools_dir = root / "tools"

    @property
    def state(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads((self.root / "uv-state.json").read_text())
        return loaded

    @state.setter
    def state(self, value: dict) -> None:
        (self.root / "uv-state.json").write_text(json.dumps(value, indent=1))

    def calls(self) -> list[list[str]]:
        path = self.root / "uv-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]

    def set_installed(
        self, name: str, version: str, commands: list[str], icon: str | None = None
    ) -> None:
        state = self.state
        state["tools"][name] = {"version": version, "commands": commands}
        self.bin.mkdir(parents=True, exist_ok=True)
        for cmd in commands:
            stub = self.bin / cmd
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        site = self.tools_dir / name / "lib" / "python3.12" / "site-packages"
        site.mkdir(parents=True, exist_ok=True)
        if icon:
            (site / icon).parent.mkdir(parents=True, exist_ok=True)
            (site / icon).write_bytes(b"\x89PNG fake")
        self.state = state

    def set_canned(
        self, name: str, commands: list[str], icon: str | None = None
    ) -> None:
        state = self.state
        state.setdefault("canned_commands", {})[name] = commands
        if icon:
            state.setdefault("icons", {})[name] = icon
        self.state = state

    def set_latest(self, name: str, version: str) -> None:
        state = self.state
        state.setdefault("latest", {})[name] = version
        self.state = state

    def set_latest_pre(self, name: str, version: str) -> None:
        """The version an install resolves to only when pre-releases are allowed."""
        state = self.state
        state.setdefault("latest_pre", {})[name] = version
        self.state = state

    def fail_next(self) -> None:
        state = self.state
        state["fail_next"] = True
        self.state = state


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated home; XDG and APPDATA variables are cleared so defaults derive from it."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv(ts.CATALOG_ENV, raising=False)
    monkeypatch.setenv(ts.OFFLINE_ENV, "1")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def fake_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path) -> FakeUv:
    if sys.platform == "win32":
        pytest.skip("the fake uv is a shebang script")
    root = tmp_path / "fakeuv"
    (root / "bin").mkdir(parents=True)
    (root / "tools").mkdir()
    script = root / "bin" / "uv"
    script.write_text(
        FAKE_UV_SCRIPT.replace("@@PYTHON@@", sys.executable).replace(
            "@@ROOT@@", repr(str(root))
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (root / "uv-state.json").write_text(
        json.dumps(
            {"tools": {}, "bin": str(root / "bin"), "tools_dir": str(root / "tools")}
        )
    )
    monkeypatch.setenv(
        "PATH", f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"
    )
    monkeypatch.delenv("UV", raising=False)
    return FakeUv(root)


@pytest.fixture
def pypi(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, dict]], ts.Fetcher]:
    """Return a factory for a dict-backed fetcher; also disables offline mode."""
    monkeypatch.delenv(ts.OFFLINE_ENV, raising=False)

    def make(records: dict[str, dict]) -> ts.Fetcher:
        def fetch(url: str, timeout: float) -> bytes:
            for name, record in records.items():
                if url == f"https://pypi.org/pypi/{name}/json":
                    return json.dumps(record).encode()
            raise OSError(f"no fake record for {url}")

        return fetch

    return make


def pypi_record(name: str, version: str, **info: object) -> dict:
    """The subset of PyPI's JSON the App Center reads."""
    base: dict[str, object] = {
        "name": name,
        "version": version,
        "summary": f"{name} summary",
        "author": "Sandia National Laboratories",
        "project_urls": {"Homepage": f"https://github.com/sandialabs/{name}"},
        "requires_python": ">=3.11",
    }
    base.update(info)
    return {"info": base, "urls": [{"upload_time_iso_8601": "2026-09-01T12:00:00Z"}]}


SMALL_CATALOG = """\
schema_version = 1
name = "Test"

[[apps]]
id = "vault"
package = "talkpipe-vault"
command = "vault-server"
args = ["--resume"]
kind = "web"
port = 18002
health = "/api/health"
opens_browser = true
icon = "talkpipe_vault/apps/static/icon-256.png"
data = ["~/.talkpipe-vault"]
needs = ["ollama"]

[[apps]]
id = "tool"
package = "some-tool"
command = "some-tool"
"""


@pytest.fixture
def catalog() -> ts.Catalog:
    return ts.parse_catalog(SMALL_CATALOG, source="<test>")


@pytest.fixture
def ctx(catalog: ts.Catalog, fake_uv: FakeUv, home: Path) -> ts.Context:
    """A context wired to the fake uv, offline, on Linux, with a recording opener."""
    opened: list[str] = []
    runs: list[list[str]] = []
    context = ts.Context(
        catalog=catalog,
        uv=ts.Uv(str(fake_uv.exe)),
        home=home,
        platform="linux",
        state_dir=home / ".local" / "state" / "talkpipe-appcenter",
        fetch=lambda url, timeout: (_ for _ in ()).throw(OSError("offline")),
        offline=True,
        shortcut_run=lambda argv: runs.append(list(argv)),
        open_url=lambda url: opened.append(url),
    )
    context.opened = opened  # type: ignore[attr-defined]
    context.runs = runs  # type: ignore[attr-defined]
    return context
