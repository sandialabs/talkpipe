"""PyPI metadata, status probes, and the refresh that combines them."""

from __future__ import annotations

import dataclasses
import http.server
import json
import socket
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import talkpipe_appcenter as ts
from conftest import FakeUv, pypi_record


def test_fetch_package_info_reads_the_pypi_shape(
    pypi: Callable[[dict], ts.Fetcher],
) -> None:
    fetch = pypi({"talkpipe-vault": pypi_record("talkpipe-vault", "1.0.0")})

    info = ts.fetch_package_info("talkpipe-vault", fetch=fetch)

    assert info == ts.PackageInfo(
        name="talkpipe-vault",
        summary="talkpipe-vault summary",
        author="Sandia National Laboratories",
        homepage="https://github.com/sandialabs/talkpipe-vault",
        latest="1.0.0",
        released="2026-09-01",
        requires_python=">=3.11",
    )


def test_fetch_package_info_tolerates_failures_and_gaps(
    pypi: Callable[[dict], ts.Fetcher],
) -> None:
    assert ts.fetch_package_info("nope", fetch=pypi({})) is None
    assert ts.fetch_package_info("x", fetch=lambda u, t: b"not json") is None
    assert ts.fetch_package_info("x", fetch=lambda u, t: b"[]") is None
    bare = ts.fetch_package_info(
        "x",
        fetch=lambda u, t: json.dumps(
            {"info": {"version": "2", "author_email": "Ann <a@b>"}, "urls": []}
        ).encode(),
    )
    assert bare == ts.PackageInfo(name="x", author="Ann", latest="2")


def test_describe_prefers_catalog_overrides_then_pypi_then_bare_name() -> None:
    entry = ts.parse_catalog(
        'schema_version = 1\n[[apps]]\nid = "aa"\npackage = "some-pkg"\ncommand = "a"\ndescription = "Mine"\n'
    ).apps[0]
    info = ts.PackageInfo(
        "Some Pkg", summary="Theirs", author="Them", homepage="https://h", latest="3"
    )

    view = ts.describe(entry, info)
    assert (view.name, view.description, view.publisher, view.latest) == (
        "Some Pkg",
        "Mine",
        "Them",
        "3",
    )

    bare = ts.describe(entry, None)
    assert (bare.name, bare.description, bare.publisher, bare.latest) == (
        "some-pkg",
        "Mine",
        "",
        None,
    )


class _Handler(http.server.BaseHTTPRequestHandler):
    ok_paths: set[str] = set()  # noqa: RUF012 - swapped per test

    def do_GET(self) -> None:
        self.send_response(200 if self.path in self.ok_paths else 404)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def http_server() -> Iterator[http.server.HTTPServer]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def _web_entry(port: int, health: str | None) -> ts.AppEntry:
    text = f'schema_version = 1\n[[apps]]\nid = "ww"\npackage = "w"\ncommand = "w"\nkind = "web"\nport = {port}\n'
    if health:
        text += f'health = "{health}"\n'
    return ts.parse_catalog(text).apps[0]


def test_app_running_with_declared_health(
    http_server: http.server.HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = http_server.server_address[1]
    monkeypatch.setattr(_Handler, "ok_paths", {"/api/health"})

    assert ts.app_running(_web_entry(port, "/api/health")) is True
    assert ts.app_running(_web_entry(port, "/other")) is False


def test_app_running_falls_back_to_common_paths_then_tcp(
    http_server: http.server.HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    port = http_server.server_address[1]
    monkeypatch.setattr(_Handler, "ok_paths", {"/health"})
    assert ts.app_running(_web_entry(port, None)) is True
    monkeypatch.setattr(_Handler, "ok_paths", set())
    assert (
        ts.app_running(_web_entry(port, None)) is True
    )  # something listens; TCP says so


def test_app_running_when_nothing_listens_and_for_cli() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    assert ts.app_running(_web_entry(port, "/health")) is False
    assert ts.app_running(_web_entry(port, None)) is False
    cli = ts.parse_catalog(
        'schema_version = 1\n[[apps]]\nid = "cc"\npackage = "c"\ncommand = "c"\n'
    ).apps[0]
    assert ts.app_running(cli) is None


def test_port_in_use_and_tcp_open_agree_on_a_real_listener() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        assert ts._port_in_use("127.0.0.1", port)
        assert ts.tcp_open("0.0.0.0", port)  # nosec B104 - wildcard mapped to loopback
    finally:
        listener.close()
    assert not ts._port_in_use("127.0.0.1", port)
    assert not ts.tcp_open("127.0.0.1", port)


def test_ollama_available_by_binary_or_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ts.shutil, "which", lambda name: "/usr/bin/ollama")
    assert ts.ollama_available(fetch=lambda u, t: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(ts.shutil, "which", lambda name: None)
    assert ts.ollama_available(fetch=lambda u, t: b"{}")
    assert not ts.ollama_available(fetch=lambda u, t: (_ for _ in ()).throw(OSError()))


def test_refresh_combines_tools_pypi_and_launcher(
    ctx: ts.Context, fake_uv: FakeUv, pypi: Callable[[dict], ts.Fetcher]
) -> None:
    fake_uv.set_installed(
        "talkpipe-vault",
        "1.0.0",
        ["vault-server", "vault-tui"],
        icon="talkpipe_vault/apps/static/icon-256.png",
    )
    ctx.offline = False
    ctx.fetch = pypi(
        {
            "talkpipe-vault": pypi_record("talkpipe-vault", "1.0.1"),
            "some-tool": pypi_record("some-tool", "0.5"),
        }
    )

    ts.refresh(ctx)

    vault = ctx.catalog.find("vault")
    tool = ctx.catalog.find("tool")
    assert vault is not None
    assert tool is not None
    status = ctx.status(vault)
    assert status.installed == "1.0.0"
    assert status.latest == "1.0.1"
    assert status.upgradable
    assert status.label == "upgrade available"
    assert status.running is False
    assert status.commands == ("vault-server", "vault-tui")
    assert status.command_path == fake_uv.bin / "vault-server"
    assert not status.launcher
    other = ctx.status(tool)
    assert other.installed is None
    assert other.latest == "0.5"
    assert other.label == "not installed"
    assert other.running is None
    assert ctx.view(vault).name == "talkpipe-vault"
    assert ctx.view(vault).publisher == "Sandia National Laboratories"


def test_refresh_offline_and_direct_packages_skip_pypi(ctx: ts.Context) -> None:
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        return b"{}"

    ctx.fetch = fetch
    ctx.offline = True

    ts.refresh(ctx)
    assert [c for c in calls if "pypi.org" in c] == []

    ctx.offline = False
    direct = dataclasses.replace(
        ctx.catalog.apps[0], package=ts.parse_package("talkpipe-vault @ /x.whl")
    )
    ctx.catalog = dataclasses.replace(ctx.catalog, apps=(direct, ctx.catalog.apps[1]))
    ts.refresh(ctx)
    assert [c for c in calls if "pypi.org" in c] == [
        "https://pypi.org/pypi/some-tool/json"
    ]


def test_find_icon_catalog_path_then_fallback(tmp_path: Path) -> None:
    env = tmp_path / "env"
    site = env / "lib" / "python3.12" / "site-packages"
    entry = ts.parse_catalog(ts.EMBEDDED_CATALOG).apps[0]
    assert ts.find_icon(entry, None) == (None, None)
    assert ts.find_icon(entry, env) == (None, None)

    (site / "talkpipe_vault" / "apps" / "static").mkdir(parents=True)
    png = site / "talkpipe_vault" / "apps" / "static" / "icon-256.png"
    png.write_bytes(b"png")
    assert ts.find_icon(entry, env) == (png, None)
    ico = png.with_suffix(".ico")
    ico.write_bytes(b"ico")
    assert ts.find_icon(entry, env) == (png, ico)

    moved = dataclasses.replace(entry, icon="talkpipe_vault/gone.png")
    assert ts.find_icon(moved, env) == (png, ico)  # fallback glob finds icon*.png
    (site / "pkg.dist-info").mkdir()
    (site / "pkg.dist-info" / "icon-999.png").write_bytes(b"")
    assert ts.find_icon(moved, env)[0] == png
