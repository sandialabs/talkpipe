# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=8,<9"]
# ///
"""TalkPipe App Center: install, launch, and manage applications with uv.

The App Center is the part of TalkPipe that installs applications, and this
one file is the whole of it (it lives outside the ``talkpipe`` package and
imports nothing from it). Run it with uv, which fetches the Python and the
one dependency (Textual) it needs into a cached environment::

    uv run https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py

With no arguments on a terminal it opens an app-store-like screen: every
application in the catalog with its installed and latest versions, whether it
is running, and whether it has a desktop launcher; keys install, upgrade,
uninstall, launch, open in the browser, and add or remove the launcher. The
same actions are available as subcommands (``list``, ``install``, ...) for
scripts and for people who prefer typing.

It ships with a catalog of the TalkPipe applications, but it is not limited
to them. Applications need no awareness of the App Center: anything on PyPI
(or a private index) that installs a console script can be listed; ``uv tool install`` puts
it in its own environment with its own Python, so nothing else on the machine
is touched. The catalog -- TOML, embedded here by default, overlaid with
``--catalog <url-or-path>`` (``--remember`` or ``catalog add`` keeps one for
every later run) -- adds only what PyPI cannot say: how to launch
the app, which port it serves, how to tell it is running, where its icon and
data live, and which external services it needs. Names, summaries, publishers,
homepages, and latest versions come from PyPI at run time, so a catalog does
not go stale when the software it lists releases.

Sections, in order: constants and version; catalog model; PyPI metadata; the
uv wrapper; status probes; the desktop-launcher writer; actions shared by the
CLI and the TUI; the CLI; the TUI; ``main``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import errno
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess  # nosec B404
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

# --- constants and version ------------------------------------------------------

STAMPED_VERSION = "0.0.0+unknown"
"""Replaced with the talkpipe release tag by CI when the file is attached to a release.

A file run from a URL has no package metadata to ask, so this is how a
released copy knows which talkpipe release it shipped with. The value here
means "development copy" (a file taken from the repository's main branch).
"""

__version__ = STAMPED_VERSION

APPCENTER_URL = "https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py"
"""Where the released copy of this file lives; the desktop launcher runs it."""

DEFAULT_PYTHON = "3.12"
"""The Python uv installs applications with (inside the CI matrix of the suite)."""

CATALOG_ENV = "TALKPIPE_APPCENTER_CATALOG"
"""Extra catalogs, ``os.pathsep``-separated, overlaid on the default."""

SAVED_CATALOGS_FILENAME = "catalogs.txt"
"""Catalogs saved with ``--remember`` / ``catalog add``, one per line, in the config dir."""

OFFLINE_ENV = "TALKPIPE_APPCENTER_OFFLINE"
"""Set to skip every PyPI lookup (latest versions show as ``?``)."""

PYPI_TIMEOUT = 3.0
MAX_CATALOG_BYTES = 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
KINDS = ("cli", "web", "tui")
HEALTH_FALLBACKS = ("/health", "/api/health")
APPCENTER_ROW_ID = "appcenter"
"""Id of the built-in row for the App Center itself (launcher only, never installed)."""

EMBEDDED_CATALOG = """\
schema_version = 1
name = "TalkPipe"
description = "Applications built on the TalkPipe framework"

[[apps]]
id = "vault"
name = "TalkPipe Vault"
package = "talkpipe-vault"
command = "vault-server"
args = ["--resume"]
kind = "web"
port = 8002
health = "/api/health"
opens_browser = true
icon = "talkpipe_vault/apps/static/icon-256.png"
data = ["~/.talkpipe-vault"]
needs = ["ollama"]

[[apps]]
id = "writing-assistant"
name = "TalkPipe Writing Assistant"
package = "talkpipe-writing-assistant"
command = "writing-assistant"
kind = "web"
port = 8001
health = "/health"
opens_browser = true
icon = "writing_assistant/app/static/android-chrome-512x512.png"
data = ["~/.writing_assistant"]
needs = ["ollama"]

[[apps]]
id = "talkpipe"
name = "ChatterLang Workbench"
package = "talkpipe[all]"
command = "chatterlang_workbench"
kind = "web"
port = 4143
icon = "talkpipe/app/static/talkpipe_logo.png"
"""
"""The default catalog; ``appcenter/talkpipe.toml`` in the repository is the same text."""

Fetcher = Callable[[str, float], bytes]
"""Fetches a URL's body within a timeout; raises OSError on any failure."""

LineSink = Callable[[str], None]
"""Receives one line of progress output at a time."""


def _http_get(url: str, timeout: float) -> bytes:
    """Default fetcher: plain urllib GET with a User-Agent PyPI accepts."""
    request = urllib.request.Request(
        url, headers={"User-Agent": f"talkpipe-appcenter/{__version__}"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        return bytes(response.read(MAX_CATALOG_BYTES + 1))


# --- catalog model ------------------------------------------------------------


class CatalogError(ValueError):
    """The catalog text is not something the App Center can act on."""


_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
_REQ_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?P<extras>\[[A-Za-z0-9._,\s-]*\])?"
    r"\s*(?P<version>==\s*[A-Za-z0-9.+!*-]+)?$"
)


def normalize_name(name: str) -> str:
    """PEP 503 normalisation, the spelling ``uv tool list`` and PyPI use."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class PackageSpec:
    """A catalog ``package`` value, split into what uv needs.

    ``name`` is the distribution name (normalised); ``requirement`` is what
    goes after ``--from`` (extras and pin included); ``reference`` is set for
    the ``name @ <url-or-path>`` form, which installs from that location.
    """

    name: str
    requirement: str
    reference: str | None = None

    @property
    def is_direct(self) -> bool:
        return self.reference is not None


def parse_package(text: str) -> PackageSpec:
    """Parse ``name[extras][==version]`` or ``name @ <url-or-path>``."""
    value = text.strip()
    if "@" in value:
        head, _, ref = value.partition("@")
        name = head.strip()
        ref = ref.strip()
        if not _NAME_RE.match(name) or not ref:
            raise CatalogError(
                f"package {text!r}: expected 'name @ <url-or-path>' with a plain "
                "distribution name before the @"
            )
        return PackageSpec(normalize_name(name), ref, ref)
    match = _REQ_RE.match(value)
    if not match or not _NAME_RE.match(match.group("name")):
        raise CatalogError(
            f"package {text!r}: expected 'name', 'name[extras]', 'name==version', "
            "or 'name @ <url-or-path>'"
        )
    return PackageSpec(normalize_name(match.group("name")), value)


_APP_FIELDS: dict[str, type | tuple[type, ...]] = {
    "id": str,
    "package": str,
    "command": str,
    "args": list,
    "kind": str,
    "port": int,
    "health": str,
    "url": str,
    "opens_browser": bool,
    "icon": str,
    "data": list,
    "needs": list,
    "index": str,
    "release": str,
    "name": str,
    "description": str,
    "publisher": str,
    "homepage": str,
}
_CATALOG_FIELDS = {"schema_version", "name", "description", "apps"}


@dataclass(frozen=True)
class AppEntry:
    """One catalog entry: how to install and launch a package."""

    id: str
    package: PackageSpec
    command: str
    args: tuple[str, ...] = ()
    kind: str = "cli"
    port: int | None = None
    health: str | None = None
    url: str | None = None
    opens_browser: bool = False
    icon: str | None = None
    data: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    index: str | None = None
    release: str | None = None
    name: str | None = None
    description: str | None = None
    publisher: str | None = None
    homepage: str | None = None

    @property
    def app_id(self) -> str:
        """Identifier used for launcher file names; matches the apps' own."""
        return self.id if self.id.startswith("talkpipe-") else f"talkpipe-{self.id}"

    @property
    def is_web(self) -> bool:
        return self.kind == "web"

    @property
    def launch_url(self) -> str:
        if self.url:
            return self.url.replace("{port}", str(self.port))
        return f"http://127.0.0.1:{self.port}/"

    @property
    def install_requirement(self) -> str:
        """What follows ``--from``: the requirement with any release pin applied."""
        if self.package.is_direct:
            return self.package.requirement
        if self.release:
            base = self.package.requirement.split("==", 1)[0].strip()
            return f"{base}=={self.release}"
        return self.package.requirement


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    name: str
    description: str
    apps: tuple[AppEntry, ...]
    sources: tuple[str, ...] = ()

    def find(self, app_id: str) -> AppEntry | None:
        for entry in self.apps:
            if entry.id == app_id:
                return entry
        return None


def _check_type(
    where: str, key: str, value: object, expected: type | tuple[type, ...]
) -> None:
    if isinstance(value, bool) and expected is not bool:
        raise CatalogError(
            f"{where}: {key} must be {_type_name(expected)}, not a boolean"
        )
    if not isinstance(value, expected):
        raise CatalogError(f"{where}: {key} must be {_type_name(expected)}")


def _type_name(expected: type | tuple[type, ...]) -> str:
    names = {str: "a string", int: "an integer", bool: "true or false", list: "a list"}
    if isinstance(expected, tuple):
        return " or ".join(names.get(t, t.__name__) for t in expected)
    return names.get(expected, expected.__name__)


def _string_list(where: str, key: str, value: object) -> tuple[str, ...]:
    _check_type(where, key, value, list)
    items = value if isinstance(value, list) else []
    for item in items:
        if not isinstance(item, str):
            raise CatalogError(f"{where}: every item of {key} must be a string")
    return tuple(items)


def _parse_entry(raw: Mapping[str, Any], source: str, position: int) -> AppEntry:
    where = f"{source}: apps[{position}]"
    unknown = sorted(set(raw) - set(_APP_FIELDS))
    if unknown:
        raise CatalogError(f"{where}: unknown key(s) {', '.join(unknown)}")
    for key in ("id", "package", "command"):
        if key not in raw:
            raise CatalogError(f"{where}: missing required key {key}")
    for key, value in raw.items():
        _check_type(where, key, value, _APP_FIELDS[key])
    app_id = raw["id"]
    if not ID_RE.match(app_id):
        raise CatalogError(
            f"{where}: id {app_id!r} must be 2-63 lowercase letters, digits, or hyphens"
        )
    where = f"{source}: app {app_id!r}"
    package = parse_package(raw["package"])
    kind = raw.get("kind", "cli")
    if kind not in KINDS:
        raise CatalogError(f"{where}: kind must be one of {', '.join(KINDS)}")
    port = raw.get("port")
    if kind == "web" and port is None:
        raise CatalogError(f"{where}: a web app needs a port")
    if port is not None and not 1 <= port <= 65535:
        raise CatalogError(f"{where}: port must be between 1 and 65535")
    health = raw.get("health")
    if health is not None and not health.startswith("/"):
        raise CatalogError(f"{where}: health must be a path starting with /")
    index = raw.get("index")
    if index is not None:
        _check_catalog_url(where, index, allow_http_loopback=True)
    release = raw.get("release")
    if release is not None and package.is_direct:
        raise CatalogError(f"{where}: release cannot pin a 'name @ <location>' package")
    if release is not None and "==" in package.requirement:
        raise CatalogError(f"{where}: give the version once, as release or as ==")
    return AppEntry(
        id=app_id,
        package=package,
        command=raw["command"].strip(),
        args=_string_list(where, "args", raw.get("args", [])),
        kind=kind,
        port=port,
        health=health,
        url=raw.get("url"),
        opens_browser=raw.get("opens_browser", False),
        icon=raw.get("icon"),
        data=_string_list(where, "data", raw.get("data", [])),
        needs=_string_list(where, "needs", raw.get("needs", [])),
        index=index,
        release=release,
        name=raw.get("name"),
        description=raw.get("description"),
        publisher=raw.get("publisher"),
        homepage=raw.get("homepage"),
    )


def _check_catalog_url(where: str, url: str, *, allow_http_loopback: bool) -> None:
    if url.startswith("https://"):
        return
    if url.startswith("http://") and allow_http_loopback:
        host = url[len("http://") :].split("/", 1)[0].split(":", 1)[0]
        if host in ("localhost", "127.0.0.1", "::1", "[::1]"):
            return
    raise CatalogError(
        f"{where}: {url!r} must be an https:// URL (http only for localhost)"
    )


def parse_catalog(text: str, *, source: str = "<catalog>") -> Catalog:
    """Parse catalog TOML; unknown or mistyped keys are errors, not warnings."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(f"{source}: not valid TOML: {exc}") from None
    unknown = sorted(set(raw) - _CATALOG_FIELDS)
    if unknown:
        raise CatalogError(f"{source}: unknown top-level key(s) {', '.join(unknown)}")
    version = raw.get("schema_version")
    if version != 1:
        raise CatalogError(f"{source}: schema_version must be 1 (got {version!r})")
    for key in ("name", "description"):
        if key in raw:
            _check_type(source, key, raw[key], str)
    apps_raw = raw.get("apps")
    if not isinstance(apps_raw, list) or not apps_raw:
        raise CatalogError(
            f"{source}: apps must be a non-empty list of [[apps]] tables"
        )
    apps: list[AppEntry] = []
    seen: set[str] = set()
    for position, item in enumerate(apps_raw):
        if not isinstance(item, dict):
            raise CatalogError(f"{source}: apps[{position}] must be a table")
        entry = _parse_entry(item, source, position)
        if entry.id in seen:
            raise CatalogError(f"{source}: duplicate app id {entry.id!r}")
        seen.add(entry.id)
        apps.append(entry)
    return Catalog(
        schema_version=1,
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        apps=tuple(apps),
        sources=(source,),
    )


def load_catalog(source: str, *, fetch: Fetcher = _http_get) -> Catalog:
    """Load a catalog from an https URL (http for localhost) or a local path."""
    if "://" in source:
        _check_catalog_url(source, source, allow_http_loopback=True)
        try:
            data = fetch(source, 10.0)
        except OSError as exc:
            raise CatalogError(f"could not fetch catalog {source}: {exc}") from None
    else:
        path = Path(source).expanduser()
        if path.is_dir():
            path = path / "talkpipe-appcenter.toml"
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CatalogError(
                f"could not read catalog {path}: {exc.strerror}"
            ) from None
    if len(data) > MAX_CATALOG_BYTES:
        raise CatalogError(f"catalog {source} is larger than {MAX_CATALOG_BYTES} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CatalogError(f"catalog {source} is not UTF-8 text") from None
    return parse_catalog(text, source=source)


def merge_catalogs(base: Catalog, *overlays: Catalog) -> Catalog:
    """Overlay catalogs on ``base``; a later entry with the same id replaces."""
    entries: dict[str, AppEntry] = {entry.id: entry for entry in base.apps}
    name, description = base.name, base.description
    sources = list(base.sources)
    for overlay in overlays:
        for entry in overlay.apps:
            entries[entry.id] = entry
        name = overlay.name or name
        description = overlay.description or description
        sources.extend(overlay.sources)
    return Catalog(1, name, description, tuple(entries.values()), tuple(sources))


def resolve_catalog(
    sources: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    use_default: bool = True,
    fetch: Fetcher = _http_get,
    saved: Sequence[str] = (),
) -> Catalog:
    """The catalog to act on: embedded default, then saved, env, and argument overlays."""
    env = os.environ if env is None else env
    from_env = env.get(CATALOG_ENV, "")
    wanted: list[str] = []
    for item in [*saved, *from_env.split(os.pathsep), *sources]:
        item = item.strip()
        if item and item not in wanted:
            wanted.append(item)
    overlays: list[Catalog] = []
    for item in wanted:
        try:
            overlays.append(load_catalog(item, fetch=fetch))
        except CatalogError as exc:
            if item in saved:
                raise CatalogError(
                    f"{exc} (a saved catalog; forget it with: catalog remove {item})"
                ) from None
            raise
    if use_default:
        return merge_catalogs(
            parse_catalog(EMBEDDED_CATALOG, source="<built-in>"), *overlays
        )
    if not overlays:
        raise CatalogError("--no-default-catalog needs at least one --catalog")
    return merge_catalogs(overlays[0], *overlays[1:])


def default_config_dir(
    platform: str = sys.platform, env: Mapping[str, str] | None = None
) -> Path:
    """Where settings that outlive a run (the saved catalogs) are kept."""
    env = os.environ if env is None else env
    if platform == "win32":
        base = env.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / "talkpipe-appcenter"
    configured = env.get("XDG_CONFIG_HOME")
    root = Path(configured) if configured else Path.home() / ".config"
    return root / "talkpipe-appcenter"


def saved_catalogs_path(
    platform: str = sys.platform, env: Mapping[str, str] | None = None
) -> Path:
    return default_config_dir(platform, env) / SAVED_CATALOGS_FILENAME


def normalize_catalog_source(source: str) -> str:
    """URLs as given; local paths made absolute so a saved one works from any directory."""
    source = source.strip()
    if "://" in source:
        return source
    return str(Path(source).expanduser().resolve())


def read_saved_catalogs(path: Path) -> list[str]:
    """The saved sources in order; blank lines, ``#`` comments, and repeats are skipped."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise CatalogError(
            f"could not read the saved catalogs {path}: {exc.strerror}"
        ) from None
    sources: list[str] = []
    for line in text.splitlines():
        item = line.strip()
        if item and not item.startswith("#") and item not in sources:
            sources.append(item)
    return sources


def write_saved_catalogs(path: Path, sources: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Catalogs the TalkPipe App Center loads on every run, one URL or path per line.\n"
        "# Managed by `catalog add` / `catalog remove`; editing by hand is fine too.\n"
    )
    path.write_text(header + "".join(f"{s}\n" for s in sources), encoding="utf-8")


def save_catalogs(path: Path, sources: Iterable[str]) -> list[str]:
    """Add ``sources`` to the saved list, skipping ones already there; returns the added."""
    saved = read_saved_catalogs(path)
    added: list[str] = []
    for source in sources:
        item = normalize_catalog_source(source)
        if item not in saved:
            saved.append(item)
            added.append(item)
    if added:
        write_saved_catalogs(path, saved)
    return added


def forget_catalog(path: Path, source: str) -> bool:
    """Remove one saved source, as typed or as normalised; False if it was not saved."""
    saved = read_saved_catalogs(path)
    matches = {source.strip(), normalize_catalog_source(source)}
    remaining = [s for s in saved if s not in matches]
    if len(remaining) == len(saved):
        return False
    write_saved_catalogs(path, remaining)
    return True


# --- PyPI metadata --------------------------------------------------------------


@dataclass(frozen=True)
class PackageInfo:
    """What PyPI knows about a distribution (its JSON API)."""

    name: str
    summary: str = ""
    author: str = ""
    homepage: str = ""
    latest: str | None = None
    released: str = ""
    requires_python: str = ""
    yanked: bool = False


def fetch_package_info(name: str, *, fetch: Fetcher = _http_get) -> PackageInfo | None:
    """PyPI's record for ``name``, or None when it cannot be fetched or parsed."""
    try:
        payload = json.loads(fetch(f"https://pypi.org/pypi/{name}/json", PYPI_TIMEOUT))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("info"), dict):
        return None
    info = payload["info"]
    urls = payload.get("urls") or []
    released = ""
    if urls and isinstance(urls[0], dict):
        released = str(
            urls[0].get("upload_time_iso_8601") or urls[0].get("upload_time") or ""
        )
    project_urls = info.get("project_urls") or {}
    homepage = ""
    for key in ("Homepage", "homepage", "Repository", "Source", "Documentation"):
        if isinstance(project_urls, dict) and project_urls.get(key):
            homepage = str(project_urls[key])
            break
    if not homepage and info.get("home_page"):
        homepage = str(info["home_page"])
    author = str(info.get("author") or "")
    if not author and info.get("author_email"):
        author = str(info["author_email"]).split("<", 1)[0].strip().strip('"')
    return PackageInfo(
        name=str(info.get("name") or name),
        summary=str(info.get("summary") or ""),
        author=author,
        homepage=homepage,
        latest=str(info["version"]) if info.get("version") else None,
        released=released[:10],
        requires_python=str(info.get("requires_python") or ""),
        yanked=bool(info.get("yanked", False)),
    )


@dataclass(frozen=True)
class AppView:
    """What the screen shows for an entry: catalog overrides over PyPI values."""

    entry: AppEntry
    name: str
    description: str
    publisher: str
    homepage: str
    latest: str | None
    released: str


def describe(entry: AppEntry, info: PackageInfo | None) -> AppView:
    pypi = info or PackageInfo(name=entry.package.name)
    return AppView(
        entry=entry,
        name=entry.name or pypi.name or entry.package.name,
        description=entry.description or pypi.summary,
        publisher=entry.publisher or pypi.author,
        homepage=entry.homepage or pypi.homepage,
        latest=pypi.latest,
        released=pypi.released,
    )


# --- uv wrapper ----------------------------------------------------------------


class UvError(RuntimeError):
    """uv is missing or an invocation failed in a way the App Center cannot handle."""


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
Streamer = Callable[[Sequence[str], LineSink], int]

_PACKAGE_LINE_RE = re.compile(r"^\s*[+-] \S+==")
"""uv's one-line-per-package listing; dropped so real progress stays visible."""


def _run_capture(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        list(argv), check=False, capture_output=True, text=True, errors="replace"
    )


def _run_stream(argv: Sequence[str], sink: LineSink) -> int:
    """Run argv, forwarding merged output line by line; return the exit status."""
    with subprocess.Popen(  # nosec B603 - fixed argv, no shell
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        errors="replace",
        bufsize=1,
    ) as process:
        assert process.stdout is not None  # nosec B101 - PIPE requested above
        for line in process.stdout:
            text = line.rstrip("\n")
            if not _PACKAGE_LINE_RE.match(text):
                sink(text)
        return process.wait()


@dataclass(frozen=True)
class InstalledTool:
    """One environment ``uv tool list`` reports."""

    name: str
    version: str
    env: Path | None
    commands: dict[str, Path] = field(default_factory=dict)


_TOOL_RE = re.compile(r"^(?P<name>\S+) v(?P<version>\S+)(?: \((?P<env>.+)\))?$")
_CMD_RE = re.compile(r"^- (?P<cmd>\S+)(?: \((?P<path>.+)\))?$")


def parse_tool_list(text: str) -> dict[str, InstalledTool]:
    """Parse ``uv tool list --show-paths`` output, keyed by normalised name."""
    tools: dict[str, InstalledTool] = {}
    current: InstalledTool | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        cmd_match = _CMD_RE.match(line)
        if cmd_match:
            if current is not None:
                path = cmd_match.group("path")
                current.commands[cmd_match.group("cmd")] = (
                    Path(path) if path else Path(cmd_match.group("cmd"))
                )
            continue
        tool_match = _TOOL_RE.match(line)
        if tool_match:
            env = tool_match.group("env")
            current = InstalledTool(
                name=normalize_name(tool_match.group("name")),
                version=tool_match.group("version"),
                env=Path(env) if env else None,
            )
            tools[current.name] = current
    return tools


class Uv:
    """The handful of uv commands the App Center relies on, all argv-based.

    Works with uv 0.7 and later: ``--dry-run`` and other newer flags are
    deliberately not used.
    """

    def __init__(
        self,
        exe: str | None = None,
        *,
        run: Runner = _run_capture,
        stream: Streamer = _run_stream,
    ) -> None:
        self.exe = exe or os.environ.get("UV") or shutil.which("uv") or ""
        self._run = run
        self._stream = stream

    def require(self) -> str:
        if not self.exe:
            raise UvError(
                "uv was not found. Install it from https://docs.astral.sh/uv/ "
                "(one command), then run the App Center again."
            )
        return self.exe

    def version(self) -> str:
        result = self._run([self.require(), "--version"])
        return (
            result.stdout.strip().removeprefix("uv ").split()[0]
            if result.stdout
            else "?"
        )

    def list_tools(self) -> dict[str, InstalledTool]:
        result = self._run([self.require(), "tool", "list", "--show-paths"])
        return parse_tool_list(result.stdout + "\n" + result.stderr)

    def bin_dir(self) -> Path:
        result = self._run([self.require(), "tool", "dir", "--bin"])
        text = result.stdout.strip()
        if result.returncode != 0 or not text:
            return Path.home() / ".local" / "bin"
        return Path(text).resolve()

    def install_argv(self, entry: AppEntry) -> list[str]:
        argv = [
            self.require(),
            "tool",
            "install",
            "--python",
            DEFAULT_PYTHON,
            "--upgrade",
        ]
        if entry.index:
            argv += ["--index", entry.index]
        argv += ["--from", entry.install_requirement, entry.package.name]
        return argv

    def install(self, entry: AppEntry, sink: LineSink) -> int:
        return self._stream(self.install_argv(entry), sink)

    def uninstall(self, name: str, sink: LineSink) -> int:
        return self._stream([self.require(), "tool", "uninstall", name], sink)

    def update_shell(self) -> None:
        """Best-effort: put the tool bin directory on PATH for new shells."""
        with contextlib.suppress(OSError):
            self._run([self.require(), "tool", "update-shell"])


# --- status probes ---------------------------------------------------------------


def _reachable_host(host: str) -> str:
    """Map a bind host to an address a client can actually reach."""
    wildcard_hosts = ("", "0.0.0.0", "::")  # nosec B104 - comparison, not a bind
    return "127.0.0.1" if host in wildcard_hosts else host


def _port_in_use(host: str, port: int) -> bool:
    """True when something already listens on host:port (every resolved address)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for family, socktype, proto, _, sockaddr in infos:
        try:
            sock = socket.socket(family, socktype, proto)
        except OSError:
            continue
        with sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(sockaddr)
            except OSError as exc:
                if exc.errno == errno.EADDRINUSE:
                    return True
    return False


def tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((_reachable_host(host), port), timeout=timeout):
            return True
    except OSError:
        return False


def health_ok(url: str, *, fetch: Fetcher = _http_get, timeout: float = 1.0) -> bool:
    try:
        fetch(url, timeout)
    except OSError:
        return False
    return True


def app_running(entry: AppEntry, *, fetch: Fetcher = _http_get) -> bool | None:
    """Whether a web app answers on its port; None for apps that cannot be probed.

    A declared ``health`` path is authoritative; otherwise the common health
    paths are tried before falling back to a plain TCP connect, so an
    unrelated program on the port is usually (not always) told apart.
    """
    if not entry.is_web or entry.port is None:
        return None
    base = entry.launch_url.rstrip("/")
    if entry.health:
        return health_ok(base + entry.health, fetch=fetch)
    if not tcp_open("127.0.0.1", entry.port):
        return False
    return any(health_ok(base + path, fetch=fetch) for path in HEALTH_FALLBACKS) or True


def ollama_available(*, fetch: Fetcher = _http_get) -> bool:
    if shutil.which("ollama"):
        return True
    return health_ok("http://127.0.0.1:11434/api/tags", fetch=fetch, timeout=1.0)


@dataclass(frozen=True)
class AppStatus:
    installed: str | None = None
    latest: str | None = None
    running: bool | None = None
    launcher: bool = False
    pid: int | None = None
    commands: tuple[str, ...] = ()
    env: Path | None = None
    command_path: Path | None = None

    @property
    def upgradable(self) -> bool:
        return bool(self.installed and self.latest and self.installed != self.latest)

    @property
    def label(self) -> str:
        if not self.installed:
            return "not installed"
        return "upgrade available" if self.upgradable else "installed"


# --- desktop launcher writer ------------------------------------------------------
# Ported from the applications' own --install-shortcut implementation: a
# freedesktop .desktop entry (Linux), a minimal .app bundle whose executable
# runs the command inside Terminal.app (macOS), or a Start Menu .lnk written
# through WScript.Shell from PowerShell (Windows). Every launcher opens a
# visible terminal on purpose: the apps have no tray icon or Quit command, so
# that window is how a non-technical user stops them and sees errors. The
# platform is a parameter so every branch is testable on any OS; external
# commands go through an injectable runner and are best-effort.

ShortcutRunner = Callable[[Sequence[str]], None]


class ShortcutError(RuntimeError):
    """The launcher could not be created on this platform or for this install."""


@dataclass(frozen=True)
class ShortcutSpec:
    """What the launcher should start and how it should look."""

    app_id: str
    name: str
    comment: str
    command: str
    args: tuple[str, ...] = ()
    icon_png: Path | None = None
    icon_ico: Path | None = None
    categories: str = "Office;"

    @property
    def bundle_id(self) -> str:
        return f"gov.sandia.{self.app_id}"


def _shortcut_run(argv: Sequence[str]) -> None:
    """Default runner: run the command, swallow its output, ignore its exit status.

    The helpers this runs (update-desktop-database, sips, iconutil,
    powershell) are conveniences; a desktop without one still gets its
    launcher, so a missing command is not an error either.
    """
    with contextlib.suppress(OSError):
        subprocess.run(list(argv), check=False, capture_output=True)  # nosec B603


def resolve_command(command: str) -> Path:
    """Absolute path of the console script the launcher should start.

    An absolute path is taken as-is. Otherwise the copy on PATH wins (with
    ``uv tool install`` that is the stable ``~/.local/bin/<command>``), then
    the running interpreter's script directory.
    """
    given = Path(command)
    if given.is_absolute():
        return given
    found = shutil.which(command)
    if found:
        return Path(found).absolute()
    scripts_dir = Path(sys.executable).parent
    for candidate in (scripts_dir / command, scripts_dir / f"{command}.exe"):
        if candidate.exists():
            return candidate.absolute()
    raise ShortcutError(
        f"cannot find the '{command}' command on PATH or next to {sys.executable}; "
        "is the application installed?"
    )


def install_shortcut(
    spec: ShortcutSpec,
    *,
    platform: str = sys.platform,
    home: Path | None = None,
    run: ShortcutRunner = _shortcut_run,
) -> list[Path]:
    """Create the launcher for ``platform``; return the paths written."""
    base = home if home is not None else Path.home()
    if platform.startswith("linux"):
        return _install_linux(spec, base, run)
    if platform == "darwin":
        return _install_macos(spec, base, run)
    if platform == "win32":
        return _install_windows(spec, base, run)
    raise ShortcutError(f"desktop launchers are not supported on {platform}")


def uninstall_shortcut(
    spec: ShortcutSpec,
    *,
    platform: str = sys.platform,
    home: Path | None = None,
    run: ShortcutRunner = _shortcut_run,
) -> list[Path]:
    """Remove the launcher; return the paths removed (empty when none existed)."""
    base = home if home is not None else Path.home()
    if platform.startswith("linux"):
        desktop_file, icon_file = linux_paths(spec, base)
        removed = [p for p in (desktop_file, icon_file) if _remove(p)]
        if removed:
            run(["update-desktop-database", str(desktop_file.parent)])
        return removed
    if platform == "darwin":
        bundle = macos_bundle_path(spec, base)
        return [bundle] if _remove(bundle) else []
    if platform == "win32":
        link = windows_link_path(spec, base)
        return [link] if _remove(link) else []
    raise ShortcutError(f"desktop launchers are not supported on {platform}")


def launcher_present(
    spec: ShortcutSpec, *, platform: str = sys.platform, home: Path | None = None
) -> bool:
    base = home if home is not None else Path.home()
    if platform.startswith("linux"):
        return linux_paths(spec, base)[0].is_file()
    if platform == "darwin":
        return macos_bundle_path(spec, base).is_dir()
    if platform == "win32":
        return windows_link_path(spec, base).is_file()
    return False


def _remove(path: Path) -> bool:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return True
    if path.exists() or path.is_symlink():
        path.unlink()
        return True
    return False


def _xdg_data_home(home: Path) -> Path:
    configured = os.environ.get("XDG_DATA_HOME")
    return Path(configured) if configured else home / ".local" / "share"


def linux_paths(spec: ShortcutSpec, home: Path) -> tuple[Path, Path]:
    data = _xdg_data_home(home)
    desktop_file = data / "applications" / f"{spec.app_id}.desktop"
    icon_file = data / "icons" / "hicolor" / "256x256" / "apps" / f"{spec.app_id}.png"
    return desktop_file, icon_file


def _desktop_quote(arg: str) -> str:
    escaped = arg
    for ch in ("\\", '"', "$", "`"):
        escaped = escaped.replace(ch, "\\" + ch)
    return f'"{escaped}"'


def _install_linux(spec: ShortcutSpec, home: Path, run: ShortcutRunner) -> list[Path]:
    command = resolve_command(spec.command)
    desktop_file, icon_file = linux_paths(spec, home)
    written: list[Path] = []
    has_icon = spec.icon_png is not None and spec.icon_png.is_file()
    if has_icon and spec.icon_png is not None:
        icon_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec.icon_png, icon_file)
        written.append(icon_file)
    exec_line = " ".join(_desktop_quote(a) for a in (str(command), *spec.args))
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={spec.name}",
        f"Comment={spec.comment}",
        f"Exec={exec_line}",
        "Terminal=true",
        f"Categories={spec.categories}",
        "StartupNotify=false",
    ]
    if has_icon:
        lines.append(f"Icon={spec.app_id}")
    desktop_file.parent.mkdir(parents=True, exist_ok=True)
    desktop_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    desktop_file.chmod(0o755)
    written.append(desktop_file)
    run(["update-desktop-database", str(desktop_file.parent)])
    return written


def macos_bundle_path(spec: ShortcutSpec, home: Path) -> Path:
    return home / "Applications" / f"{spec.name}.app"


def _sh_quote(arg: str) -> str:
    return "'" + arg.replace("'", "'\\''") + "'"


def _install_macos(spec: ShortcutSpec, home: Path, run: ShortcutRunner) -> list[Path]:
    command = resolve_command(spec.command)
    bundle = macos_bundle_path(spec, home)
    contents = bundle / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"
    if bundle.exists():
        shutil.rmtree(bundle)
    macos_dir.mkdir(parents=True)
    resources.mkdir(parents=True)
    run_command = resources / "run.command"
    run_command.write_text(
        "#!/bin/sh\n"
        f"exec {' '.join(_sh_quote(a) for a in (str(command), *spec.args))}\n",
        encoding="utf-8",
    )
    run_command.chmod(0o755)
    launcher = macos_dir / spec.app_id
    launcher.write_text(
        "#!/bin/sh\n"
        'here="$(cd "$(dirname "$0")" && pwd)"\n'
        'exec open -a Terminal "$here/../Resources/run.command"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    icns = resources / f"{spec.app_id}.icns"
    if spec.icon_png is not None and spec.icon_png.is_file():
        _make_icns(spec.icon_png, icns, run)
    info: dict[str, object] = {
        "CFBundleName": spec.name,
        "CFBundleDisplayName": spec.name,
        "CFBundleIdentifier": spec.bundle_id,
        "CFBundleExecutable": spec.app_id,
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0",
        "CFBundleInfoDictionaryVersion": "6.0",
        "NSHighResolutionCapable": True,
    }
    if icns.is_file():
        info["CFBundleIconFile"] = icns.name
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)
    os.utime(bundle, None)
    return [bundle]


def _make_icns(png: Path, icns: Path, run: ShortcutRunner) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            run(
                [
                    "sips",
                    "-z",
                    str(size),
                    str(size),
                    str(png),
                    "--out",
                    str(iconset / f"icon_{size}x{size}.png"),
                ]
            )
        run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)])


def windows_link_path(spec: ShortcutSpec, home: Path) -> Path:
    appdata = os.environ.get("APPDATA")
    roaming = Path(appdata) if appdata else home / "AppData" / "Roaming"
    return (
        roaming
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / (f"{spec.name}.lnk")
    )


def _ps_quote(arg: str) -> str:
    return "'" + arg.replace("'", "''") + "'"


def _install_windows(spec: ShortcutSpec, home: Path, run: ShortcutRunner) -> list[Path]:
    command = resolve_command(spec.command)
    link = windows_link_path(spec, home)
    link.parent.mkdir(parents=True, exist_ok=True)
    statements = [
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(link))})",
        f"$s.TargetPath = {_ps_quote(str(command))}",
        f"$s.Arguments = {_ps_quote(' '.join(spec.args))}",
        f"$s.WorkingDirectory = {_ps_quote(str(home))}",
        f"$s.Description = {_ps_quote(spec.comment)}",
    ]
    if spec.icon_ico is not None and spec.icon_ico.is_file():
        statements.append(f"$s.IconLocation = {_ps_quote(str(spec.icon_ico) + ',0')}")
    statements.append("$s.Save()")
    run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "; ".join(statements),
        ]
    )
    return [link]


_ICON_FALLBACK_GLOBS = (
    "**/icon*.png",
    "**/logo*.png",
    "**/*-512x512.png",
    "**/*-256x256.png",
)


def site_packages_dirs(env: Path) -> list[Path]:
    """site-packages directories of a tool environment (POSIX and Windows layouts)."""
    candidates = [*env.glob("lib/python*/site-packages"), env / "Lib" / "site-packages"]
    return [path for path in candidates if path.is_dir()]


def find_icon(entry: AppEntry, env: Path | None) -> tuple[Path | None, Path | None]:
    """The PNG (and Windows .ico) to use for ``entry``, found in its installed env.

    The catalog's ``icon`` path is tried first; a wrong or missing one falls
    back to a small set of conventional names, then to no icon at all.
    """
    if env is None:
        return None, None
    for site in site_packages_dirs(env):
        png: Path | None = None
        if entry.icon:
            candidate = site / entry.icon
            if candidate.is_file():
                png = candidate
        if png is None:
            for pattern in _ICON_FALLBACK_GLOBS:
                found = sorted(
                    p
                    for p in site.glob(pattern)
                    if not any(part.endswith(".dist-info") for part in p.parts)
                )
                if found:
                    png = found[0]
                    break
        if png is None:
            continue
        ico = png.with_suffix(".ico")
        if not ico.is_file():
            icos = sorted(png.parent.glob("*.ico"))
            ico = icos[0] if icos else ico
        return png, (ico if ico.is_file() else None)
    return None, None


# --- actions shared by the CLI and the TUI ------------------------------------------


def default_state_dir(
    platform: str = sys.platform, env: Mapping[str, str] | None = None
) -> Path:
    env = os.environ if env is None else env
    if platform == "win32":
        base = env.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "talkpipe-appcenter"
    configured = env.get("XDG_STATE_HOME")
    root = Path(configured) if configured else Path.home() / ".local" / "state"
    return root / "talkpipe-appcenter"


@dataclass
class Context:
    """Everything an action needs; built once in ``main`` and passed around.

    Every external touchpoint (uv, HTTP, the launcher's helper commands, the
    home directory, the platform) is a field so tests can substitute it.
    """

    catalog: Catalog
    uv: Uv
    home: Path = field(default_factory=Path.home)
    platform: str = sys.platform
    state_dir: Path = field(default_factory=default_state_dir)
    fetch: Fetcher = _http_get
    offline: bool = False
    shortcut_run: ShortcutRunner = _shortcut_run
    open_url: Callable[[str], object] = webbrowser.open
    tools: dict[str, InstalledTool] = field(default_factory=dict)
    infos: dict[str, PackageInfo | None] = field(default_factory=dict)
    statuses: dict[str, AppStatus] = field(default_factory=dict)

    def tool_for(self, entry: AppEntry) -> InstalledTool | None:
        return self.tools.get(entry.package.name)

    def view(self, entry: AppEntry) -> AppView:
        return describe(entry, self.infos.get(entry.package.name))

    def status(self, entry: AppEntry) -> AppStatus:
        return self.statuses.get(entry.id, AppStatus())


def refresh(ctx: Context) -> None:
    """Re-read installed tools, PyPI metadata (unless offline), and probes."""
    ctx.tools = ctx.uv.list_tools()
    names = sorted({e.package.name for e in ctx.catalog.apps})
    lookups = [n for n in names if not ctx.offline and n not in ctx.infos]
    skip = {e.package.name for e in ctx.catalog.apps if e.package.is_direct or e.index}
    lookups = [n for n in lookups if n not in skip]
    if lookups:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = pool.map(
                lambda n: (n, fetch_package_info(n, fetch=ctx.fetch)), lookups
            )
            for name, info in results:
                ctx.infos[name] = info
    ctx.statuses = {entry.id: _status_of(entry, ctx) for entry in ctx.catalog.apps}


def _status_of(entry: AppEntry, ctx: Context) -> AppStatus:
    tool = ctx.tool_for(entry)
    info = ctx.infos.get(entry.package.name)
    running = (
        app_running(entry, fetch=ctx.fetch)
        if tool
        else (None if not entry.is_web else False)
    )
    if tool is None and entry.is_web and entry.port is not None:
        running = app_running(entry, fetch=ctx.fetch)
    return AppStatus(
        installed=tool.version if tool else None,
        latest=info.latest if info else None,
        running=running,
        launcher=launcher_present(
            shortcut_spec(entry, ctx), platform=ctx.platform, home=ctx.home
        ),
        pid=_read_pid(entry, ctx),
        commands=tuple(sorted(tool.commands)) if tool else (),
        env=tool.env if tool else None,
        command_path=tool.commands.get(entry.command) if tool else None,
    )


def shortcut_spec(entry: AppEntry, ctx: Context) -> ShortcutSpec:
    view = ctx.view(entry)
    tool = ctx.tool_for(entry)
    png, ico = find_icon(entry, tool.env if tool else None)
    command_path = tool.commands.get(entry.command) if tool else None
    return ShortcutSpec(
        app_id=entry.app_id,
        name=view.name,
        comment=view.description or f"Open {view.name}",
        command=str(command_path) if command_path else entry.command,
        args=entry.args,
        icon_png=png,
        icon_ico=ico,
    )


def appcenter_shortcut_spec(ctx: Context) -> ShortcutSpec:
    """The launcher for the App Center itself: ``uv run <APPCENTER_URL>`` in a terminal."""
    return ShortcutSpec(
        app_id="talkpipe-appcenter",
        name="TalkPipe App Center",
        comment="Install and manage TalkPipe applications",
        command=ctx.uv.exe or "uv",
        args=("run", APPCENTER_URL),
    )


def _pid_file(entry: AppEntry, ctx: Context) -> Path:
    return ctx.state_dir / f"{entry.id}.pid"


def _log_file(entry: AppEntry, ctx: Context) -> Path:
    return ctx.state_dir / f"{entry.id}.log"


def _read_pid(entry: AppEntry, ctx: Context) -> int | None:
    try:
        pid = int(_pid_file(entry, ctx).read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if _process_alive(pid, ctx.platform) else None


def _process_alive(pid: int, platform: str) -> bool:
    if platform == "win32":
        result = _run_capture(["tasklist", "/FI", f"PID eq {pid}", "/NH"])
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def explain_needs(entry: AppEntry, ctx: Context) -> list[str]:
    """Human sentences about external services the entry needs."""
    notes: list[str] = []
    for need in entry.needs:
        if need == "ollama":
            if ollama_available(fetch=ctx.fetch):
                notes.append("Ollama detected: local models will work out of the box.")
            else:
                notes.append(
                    "Needs a language model: install Ollama from "
                    "https://ollama.com/download (then `ollama pull mistral-small`), "
                    "or enter an OpenAI or Anthropic API key in the app's settings."
                )
        else:
            notes.append(f"Needs {need} (not something the App Center can install).")
    return notes


def install_app(entry: AppEntry, ctx: Context, sink: LineSink) -> bool:
    view = ctx.view(entry)
    status = ctx.status(entry)
    verb = "Upgrading" if status.installed else "Installing"
    sink(f"==> {verb} {view.name} ({entry.install_requirement}) with uv")
    if not status.installed:
        sink(
            f"This can take a few minutes the first time: uv fetches Python {DEFAULT_PYTHON} "
            "if needed, then the application and its dependencies."
        )
    code = ctx.uv.install(entry, sink)
    if code != 0:
        sink(f"uv tool install failed (exit code {code}).")
        return False
    ctx.uv.update_shell()
    refresh(ctx)
    after = ctx.status(entry)
    if status.installed and status.installed == after.installed:
        sink(f"{view.name} {after.installed} is already the newest version.")
    elif status.installed:
        sink(f"Upgraded {view.name} {status.installed} -> {after.installed}.")
    else:
        sink(f"Installed {view.name} {after.installed}.")
    for note in explain_needs(entry, ctx):
        sink(note)
    return True


def uninstall_app(entry: AppEntry, ctx: Context, sink: LineSink) -> bool:
    view = ctx.view(entry)
    status = ctx.status(entry)
    if not status.installed:
        sink(f"{view.name} is not installed.")
        return True
    if status.launcher:
        remove_shortcut(entry, ctx, sink)
    sink(f"==> Uninstalling {view.name} with uv")
    code = ctx.uv.uninstall(entry.package.name, sink)
    if code != 0:
        sink(f"uv tool uninstall failed (exit code {code}).")
        return False
    if entry.data:
        sink(
            "Your data was left in place: "
            + ", ".join(entry.data)
            + ". Delete those folders yourself if you want them gone."
        )
    refresh(ctx)
    sink(f"Uninstalled {view.name}.")
    return True


@dataclass(frozen=True)
class LaunchResult:
    ok: bool
    message: str
    url: str | None = None
    pid: int | None = None


def wait_until_ready(entry: AppEntry, ctx: Context, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app_running(entry, fetch=ctx.fetch):
            return True
        time.sleep(0.5)
    return False


def launch_app(entry: AppEntry, ctx: Context, sink: LineSink) -> LaunchResult:
    """Start a web app detached (logs under the state dir) and open its page.

    A cli/tui app is run in the foreground instead; the TUI suspends itself
    around the call. If the app is already running, only the browser opens.
    """
    view = ctx.view(entry)
    status = ctx.status(entry)
    if not status.command_path:
        return LaunchResult(False, f"{view.name} is not installed.")
    if entry.is_web and status.running:
        ctx.open_url(entry.launch_url)
        return LaunchResult(
            True,
            f"{view.name} is already running; opened {entry.launch_url}",
            entry.launch_url,
        )
    argv = [str(status.command_path), *entry.args]
    if not entry.is_web:
        sink(f"==> Running {' '.join(argv)}")
        code = subprocess.call(argv)  # nosec B603 - resolved command path, no shell
        return LaunchResult(code == 0, f"{view.name} exited with status {code}.")
    ctx.state_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_file(entry, ctx)
    sink(f"==> Starting {view.name}: {' '.join(argv)}")
    sink(f"Output goes to {log_path}")
    with log_path.open("ab") as log:
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
        }
        if ctx.platform == "win32":
            kwargs["creationflags"] = (
                0x00000008 | 0x00000200
            )  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(argv, **kwargs)  # nosec B603 - resolved path, no shell
        except OSError as exc:
            return LaunchResult(False, f"could not start {view.name}: {exc}")
    _pid_file(entry, ctx).write_text(str(process.pid))
    if not wait_until_ready(entry, ctx):
        return LaunchResult(
            False,
            f"{view.name} did not answer on port {entry.port} within 30 s; see {log_path}",
            pid=process.pid,
        )
    if not entry.opens_browser:
        ctx.open_url(entry.launch_url)
    refresh(ctx)
    return LaunchResult(
        True,
        f"{view.name} is running at {entry.launch_url}",
        entry.launch_url,
        process.pid,
    )


def stop_app(entry: AppEntry, ctx: Context, sink: LineSink) -> bool:
    """Stop a web app the App Center started (it knows the pid); others cannot be stopped."""
    view = ctx.view(entry)
    pid = _read_pid(entry, ctx)
    if pid is None:
        if ctx.status(entry).running:
            sink(
                f"{view.name} is running but was not started by the App Center; close its terminal window to stop it."
            )
        else:
            sink(f"{view.name} is not running.")
        return False
    sink(f"==> Stopping {view.name} (pid {pid})")
    try:
        if ctx.platform == "win32":
            _run_capture(["taskkill", "/PID", str(pid), "/T", "/F"])
        else:
            os.killpg(pid, signal.SIGTERM)
    except OSError as exc:
        sink(f"could not stop pid {pid}: {exc}")
        return False
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _process_alive(pid, ctx.platform):
        time.sleep(0.2)
    _pid_file(entry, ctx).unlink(missing_ok=True)
    refresh(ctx)
    sink(f"Stopped {view.name}.")
    return True


def open_app(entry: AppEntry, ctx: Context, sink: LineSink) -> bool:
    view = ctx.view(entry)
    if not entry.is_web:
        sink(f"{view.name} has no web page to open.")
        return False
    if not ctx.status(entry).running:
        sink(f"{view.name} is not running; launch it first.")
        return False
    ctx.open_url(entry.launch_url)
    sink(f"Opened {entry.launch_url}")
    return True


def add_shortcut(entry: AppEntry, ctx: Context, sink: LineSink) -> list[Path]:
    view = ctx.view(entry)
    if not ctx.status(entry).installed:
        sink(f"{view.name} is not installed; install it before adding a launcher.")
        return []
    paths = install_shortcut(
        shortcut_spec(entry, ctx),
        platform=ctx.platform,
        home=ctx.home,
        run=ctx.shortcut_run,
    )
    sink(f"Added the {view.name} launcher:")
    for path in paths:
        sink(f"  {path}")
    refresh(ctx)
    return paths


def remove_shortcut(entry: AppEntry, ctx: Context, sink: LineSink) -> list[Path]:
    view = ctx.view(entry)
    paths = uninstall_shortcut(
        shortcut_spec(entry, ctx),
        platform=ctx.platform,
        home=ctx.home,
        run=ctx.shortcut_run,
    )
    sink(
        f"Removed the {view.name} launcher:"
        if paths
        else f"No {view.name} launcher was installed."
    )
    for path in paths:
        sink(f"  {path}")
    refresh(ctx)
    return paths


def add_appcenter_shortcut(ctx: Context, sink: LineSink) -> list[Path]:
    ctx.uv.require()
    paths = install_shortcut(
        appcenter_shortcut_spec(ctx),
        platform=ctx.platform,
        home=ctx.home,
        run=ctx.shortcut_run,
    )
    sink("Added the TalkPipe App Center launcher:")
    for path in paths:
        sink(f"  {path}")
    return paths


def remove_appcenter_shortcut(ctx: Context, sink: LineSink) -> list[Path]:
    paths = uninstall_shortcut(
        appcenter_shortcut_spec(ctx),
        platform=ctx.platform,
        home=ctx.home,
        run=ctx.shortcut_run,
    )
    sink(
        "Removed the TalkPipe App Center launcher."
        if paths
        else "No TalkPipe App Center launcher was installed."
    )
    return paths


def appcenter_launcher_present(ctx: Context) -> bool:
    return launcher_present(
        appcenter_shortcut_spec(ctx), platform=ctx.platform, home=ctx.home
    )


# --- CLI ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="talkpipe-appcenter",
        description=(
            "Install, launch, and manage TalkPipe applications with uv. "
            "With no subcommand on a terminal, opens the App Center screen."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"talkpipe-appcenter {__version__}"
    )
    _add_catalog_options(parser, after_subcommand=False)
    sub = parser.add_subparsers(dest="command")
    p_list = sub.add_parser("list", help="show every app with its status")
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_info = sub.add_parser("info", help="details of one app")
    p_info.add_argument("app")
    p_install = sub.add_parser("install", help="install (or upgrade) apps")
    p_install.add_argument("apps", nargs="+")
    p_upgrade = sub.add_parser("upgrade", help="upgrade installed apps")
    p_upgrade.add_argument("apps", nargs="*")
    p_upgrade.add_argument("--all", action="store_true", help="every installed app")
    p_uninstall = sub.add_parser(
        "uninstall", help="remove an app's environment and launcher"
    )
    p_uninstall.add_argument("apps", nargs="+")
    p_uninstall.add_argument(
        "-y", "--yes", action="store_true", help="do not ask for confirmation"
    )
    p_launch = sub.add_parser("launch", help="start an app (and open its page)")
    p_launch.add_argument("app")
    p_stop = sub.add_parser("stop", help="stop a web app the App Center started")
    p_stop.add_argument("app")
    p_open = sub.add_parser("open", help="open a running web app in the browser")
    p_open.add_argument("app")
    p_shortcut = sub.add_parser("shortcut", help="add or remove a desktop launcher")
    p_shortcut.add_argument("action", choices=("add", "remove"))
    p_shortcut.add_argument(
        "app", help=f"an app id, or '{APPCENTER_ROW_ID}' for the App Center itself"
    )
    p_ui = sub.add_parser("ui", help="open the App Center screen")
    for action_parser in (
        p_list,
        p_info,
        p_install,
        p_upgrade,
        p_uninstall,
        p_launch,
        p_stop,
        p_open,
        p_shortcut,
        p_ui,
    ):
        _add_catalog_options(action_parser, after_subcommand=True)
    p_catalog = sub.add_parser(
        "catalog", help="list, add, or remove the catalogs loaded on every run"
    )
    catalog_sub = p_catalog.add_subparsers(dest="catalog_action", required=True)
    catalog_sub.add_parser("list", help="show the saved catalogs")
    p_catalog_add = catalog_sub.add_parser(
        "add", help="save a catalog (https URL or local TOML file) for every later run"
    )
    p_catalog_add.add_argument("source", metavar="URL_OR_PATH")
    p_catalog_remove = catalog_sub.add_parser("remove", help="forget a saved catalog")
    p_catalog_remove.add_argument("source", metavar="URL_OR_PATH")
    return parser


def _add_catalog_options(
    parser: argparse.ArgumentParser, *, after_subcommand: bool
) -> None:
    """``--catalog``, ``--no-default-catalog``, ``--remember``: before or after the subcommand.

    A subparser writes its own defaults over the main parser's values, so the
    copies on subcommands store under a different name and
    :func:`catalog_options` merges the two.
    """
    suffix = "_after" if after_subcommand else ""
    parser.add_argument(
        "--catalog",
        dest=f"catalog{suffix}",
        action="append",
        default=[],
        metavar="URL_OR_PATH",
        help="an extra catalog (https URL or local TOML file) overlaid on the default; repeatable",
    )
    parser.add_argument(
        "--no-default-catalog",
        dest=f"no_default_catalog{suffix}",
        action="store_true",
        help="use only the --catalog files, not the built-in TalkPipe catalog",
    )
    parser.add_argument(
        "--remember",
        dest=f"remember{suffix}",
        action="store_true",
        help="also save the --catalog values so every later run loads them (see: catalog list)",
    )


def catalog_options(args: argparse.Namespace) -> tuple[list[str], bool, bool]:
    """The catalog sources, whether to keep the built-in catalog, and whether to save."""
    sources = [*args.catalog, *getattr(args, "catalog_after", [])]
    use_default = not (
        args.no_default_catalog or getattr(args, "no_default_catalog_after", False)
    )
    remember = args.remember or getattr(args, "remember_after", False)
    return sources, use_default, remember


def _print(line: str) -> None:
    print(line, flush=True)


def _entries_for(ids: Iterable[str], ctx: Context) -> list[AppEntry]:
    entries: list[AppEntry] = []
    for app_id in ids:
        entry = ctx.catalog.find(app_id)
        if entry is None:
            known = ", ".join(e.id for e in ctx.catalog.apps)
            raise SystemExit(
                f"error: no app {app_id!r} in the catalog (known: {known})"
            )
        entries.append(entry)
    return entries


def _row(entry: AppEntry, ctx: Context) -> dict[str, Any]:
    view = ctx.view(entry)
    status = ctx.status(entry)
    return {
        "id": entry.id,
        "name": view.name,
        "package": entry.package.name,
        "description": view.description,
        "publisher": view.publisher,
        "homepage": view.homepage,
        "kind": entry.kind,
        "status": status.label,
        "installed": status.installed,
        "latest": status.latest,
        "released": view.released,
        "running": status.running,
        "launcher": status.launcher,
        "commands": list(status.commands),
        "url": entry.launch_url if entry.is_web else None,
    }


def cmd_list(args: argparse.Namespace, ctx: Context) -> int:
    refresh(ctx)
    rows = [_row(entry, ctx) for entry in ctx.catalog.apps]
    if args.json:
        _print(json.dumps({"catalog": ctx.catalog.name, "apps": rows}, indent=2))
        return 0
    widths = {
        "id": max(2, *(len(r["id"]) for r in rows)),
        "name": max(4, *(len(r["name"]) for r in rows)),
    }
    _print(
        f"{'ID':<{widths['id']}}  {'NAME':<{widths['name']}}  {'STATUS':<18}  {'INSTALLED':<12}  {'LATEST':<12}  RUNNING"
    )
    for r in rows:
        running = "-" if r["running"] is None else ("yes" if r["running"] else "no")
        _print(
            f"{r['id']:<{widths['id']}}  {r['name']:<{widths['name']}}  {r['status']:<18}  "
            f"{r['installed'] or '-':<12}  {r['latest'] or '?':<12}  {running}"
        )
    _print("")
    _print("Install one with: talkpipe-appcenter install <id>")
    return 0


def cmd_info(args: argparse.Namespace, ctx: Context) -> int:
    (entry,) = _entries_for([args.app], ctx)
    refresh(ctx)
    row = _row(entry, ctx)
    _print(f"{row['name']} ({entry.id})")
    if row["description"]:
        _print(f"  {row['description']}")
    _print(f"  package:   {entry.package.requirement}")
    if row["publisher"]:
        _print(f"  publisher: {row['publisher']}")
    if row["homepage"]:
        _print(f"  homepage:  {row['homepage']}")
    latest = (
        f"{row['latest']} ({row['released']})"
        if row["released"]
        else (row["latest"] or "?")
    )
    _print(f"  latest:    {latest}")
    _print(f"  installed: {row['installed'] or '-'}  [{row['status']}]")
    _print(f"  command:   {entry.command} {' '.join(entry.args)}".rstrip())
    if row["commands"]:
        _print(f"  provides:  {', '.join(row['commands'])}")
    if entry.is_web:
        running = "-" if row["running"] is None else ("yes" if row["running"] else "no")
        _print(f"  url:       {row['url']}  (running: {running})")
    _print(f"  launcher:  {'present' if row['launcher'] else 'none'}")
    if entry.data:
        _print(f"  data:      {', '.join(entry.data)}")
    for note in explain_needs(entry, ctx):
        _print(f"  note:      {note}")
    return 0


def cmd_install(args: argparse.Namespace, ctx: Context) -> int:
    entries = _entries_for(args.apps, ctx)
    refresh(ctx)
    # Every requested install runs, even after one fails.
    results = [install_app(entry, ctx, _print) for entry in entries]
    ok = all(results)
    if ok:
        _print("")
        _print(
            "Open a NEW terminal for the commands to be on your PATH, or launch from the App Center."
        )
    return 0 if ok else 1


def cmd_upgrade(args: argparse.Namespace, ctx: Context) -> int:
    refresh(ctx)
    if args.all:
        entries = [e for e in ctx.catalog.apps if ctx.status(e).installed]
    elif args.apps:
        entries = _entries_for(args.apps, ctx)
    else:
        raise SystemExit("error: name the apps to upgrade, or pass --all")
    if not entries:
        _print("Nothing is installed.")
        return 0
    results = [install_app(entry, ctx, _print) for entry in entries]
    return 0 if all(results) else 1


def cmd_uninstall(args: argparse.Namespace, ctx: Context) -> int:
    entries = _entries_for(args.apps, ctx)
    refresh(ctx)
    for entry in entries:
        status = ctx.status(entry)
        if status.installed and not args.yes:
            commands = ", ".join(status.commands) or entry.command
            answer = input(
                f"Uninstall {ctx.view(entry).name} (removes {commands})? [y/N] "
            )
            if answer.strip().lower() not in ("y", "yes"):
                _print("Skipped.")
                continue
        if not uninstall_app(entry, ctx, _print):
            return 1
    return 0


def cmd_launch(args: argparse.Namespace, ctx: Context) -> int:
    (entry,) = _entries_for([args.app], ctx)
    refresh(ctx)
    result = launch_app(entry, ctx, _print)
    _print(result.message)
    return 0 if result.ok else 1


def cmd_stop(args: argparse.Namespace, ctx: Context) -> int:
    (entry,) = _entries_for([args.app], ctx)
    refresh(ctx)
    return 0 if stop_app(entry, ctx, _print) else 1


def cmd_open(args: argparse.Namespace, ctx: Context) -> int:
    (entry,) = _entries_for([args.app], ctx)
    refresh(ctx)
    return 0 if open_app(entry, ctx, _print) else 1


def cmd_shortcut(args: argparse.Namespace, ctx: Context) -> int:
    try:
        if args.app == APPCENTER_ROW_ID:
            if args.action == "add":
                add_appcenter_shortcut(ctx, _print)
            else:
                remove_appcenter_shortcut(ctx, _print)
            return 0
        (entry,) = _entries_for([args.app], ctx)
        refresh(ctx)
        if args.action == "add":
            return 0 if add_shortcut(entry, ctx, _print) else 1
        remove_shortcut(entry, ctx, _print)
    except ShortcutError as exc:
        _print(f"error: {exc}")
        return 1
    return 0


def cmd_catalog(args: argparse.Namespace, *, fetch: Fetcher = _http_get) -> int:
    """Saved catalogs. Runs before the catalog is resolved, so a saved one that no
    longer loads can still be listed and removed."""
    path = saved_catalogs_path()
    if args.catalog_action == "list":
        saved = read_saved_catalogs(path)
        if not saved:
            _print(f"No saved catalogs ({path}).")
            return 0
        _print(f"Saved catalogs, loaded on every run ({path}):")
        for source in saved:
            _print(f"  {source}")
        return 0
    if args.catalog_action == "add":
        load_catalog(
            args.source, fetch=fetch
        )  # a catalog that does not load is not saved
        added = save_catalogs(path, [args.source])
        if added:
            _print(f"Saved catalog {added[0]}; every run now loads it.")
        else:
            _print(f"{normalize_catalog_source(args.source)} is already saved.")
        return 0
    if forget_catalog(path, args.source):
        _print(f"Removed {args.source} from the saved catalogs.")
        return 0
    _print(f"error: {args.source} is not a saved catalog (see: catalog list)")
    return 1


COMMANDS: dict[str, Callable[[argparse.Namespace, Context], int]] = {
    "list": cmd_list,
    "info": cmd_info,
    "install": cmd_install,
    "upgrade": cmd_upgrade,
    "uninstall": cmd_uninstall,
    "launch": cmd_launch,
    "stop": cmd_stop,
    "open": cmd_open,
    "shortcut": cmd_shortcut,
}


# --- TUI --------------------------------------------------------------------------------

from textual import (  # noqa: E402 - the sections above are usable without Textual
    on,
    work,
)
from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding, BindingType  # noqa: E402
from textual.containers import Horizontal, Vertical  # noqa: E402
from textual.screen import ModalScreen  # noqa: E402
from textual.widgets import (  # noqa: E402
    Button,
    DataTable,
    Footer,
    Label,
    RichLog,
    Static,
)

COMPACT_ROWS = 24
"""Below this many rows the detail pane gives up its height for the table and log."""

APPCENTER_CSS = """
Screen { layout: vertical; }
#title { height: 1; padding: 0 1; background: $primary; color: $text; text-style: bold; }
#body { height: 1fr; }
#apps { width: 2fr; height: 1fr; }
#side { width: 1fr; height: 1fr; border-left: solid $secondary; padding: 0 1; }
#detail { height: auto; }
#needs { height: auto; color: $warning; margin-top: 1; }
#log { height: 8; border-top: solid $secondary; }
Screen.compact #log { height: 5; }
Screen.compact #side { display: none; }
ConfirmScreen { align: center middle; }
#confirm { width: 70; height: auto; border: thick $primary; background: $surface; padding: 1 2; }
#confirm-buttons { height: auto; margin-top: 1; }
#confirm-buttons Button { margin-right: 2; }
"""


class ConfirmScreen(ModalScreen[bool]):
    """A yes/no question; the answer is the screen's result."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss(False)", "Cancel")
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Label(self._question, markup=False)
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", id="yes", variant="warning")
                yield Button("No", id="no")

    @on(Button.Pressed)
    def _answer(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class AppCenterApp(App[None]):
    """The App Center screen: a table of apps, a detail pane, and a log of uv's output."""

    CSS = APPCENTER_CSS
    ENABLE_COMMAND_PALETTE = False
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("i", "install", "Install/upgrade"),
        Binding("u", "upgrade", "Upgrade", show=False),
        Binding("x", "uninstall", "Uninstall"),
        Binding("l", "launch", "Launch"),
        Binding("o", "open", "Open page"),
        Binding("s", "shortcut", "Launcher"),
        Binding("c", "close", "Stop", show=False),
        Binding("space", "select", "Select", show=False),
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self, ctx: Context) -> None:
        super().__init__()
        self.ctx = ctx
        self.selected: set[str] = set()
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Static(
            f"TalkPipe App Center {__version__}  -  {self.ctx.catalog.name}",
            id="title",
            markup=False,
        )
        with Horizontal(id="body"):
            yield DataTable(id="apps", cursor_type="row", zebra_stripes=True)
            with Vertical(id="side"):
                yield Static("", id="detail", markup=False)
                yield Static("", id="needs", markup=False)
        yield RichLog(id="log", markup=False, wrap=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#apps", DataTable)
        table.add_columns(
            "", "App", "Status", "Installed", "Latest", "Running", "Launcher"
        )
        for entry in self.ctx.catalog.apps:
            table.add_row("", entry.id, "...", "", "", "", "", key=entry.id)
        table.add_row(
            "",
            "TalkPipe App Center",
            "this program",
            __version__,
            "",
            "",
            "",
            key=APPCENTER_ROW_ID,
        )
        table.focus()
        self._apply_size()
        self.log_line(f"uv: {self.ctx.uv.exe or 'not found'}")
        self._refresh_status()

    def on_resize(self) -> None:
        self._apply_size()

    def _apply_size(self) -> None:
        self.screen.set_class(self.size.height < COMPACT_ROWS, "compact")

    # -- helpers ---------------------------------------------------------------

    def log_line(self, text: str) -> None:
        self.query_one("#log", RichLog).write(text)

    def _cursor_id(self) -> str | None:
        table = self.query_one("#apps", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return str(row_key.value) if row_key.value is not None else None

    def _targets(self) -> list[AppEntry]:
        ids = sorted(self.selected) if self.selected else [self._cursor_id() or ""]
        return [e for e in (self.ctx.catalog.find(i) for i in ids) if e is not None]

    def _render_rows(self) -> None:
        table = self.query_one("#apps", DataTable)
        for entry in self.ctx.catalog.apps:
            view = self.ctx.view(entry)
            status = self.ctx.status(entry)
            running = (
                "-" if status.running is None else ("yes" if status.running else "no")
            )
            values = [
                "*" if entry.id in self.selected else "",
                view.name,
                status.label,
                status.installed or "-",
                status.latest or "?",
                running,
                "yes" if status.launcher else "",
            ]
            for column, value in enumerate(values):
                table.update_cell(entry.id, table.ordered_columns[column].key, value)
        table.update_cell(
            APPCENTER_ROW_ID,
            table.ordered_columns[6].key,
            "yes" if appcenter_launcher_present(self.ctx) else "",
        )
        self._render_detail()

    def _render_detail(self) -> None:
        detail = self.query_one("#detail", Static)
        needs = self.query_one("#needs", Static)
        app_id = self._cursor_id()
        if app_id == APPCENTER_ROW_ID:
            detail.update(
                "TalkPipe App Center\n\nThis program. Press s to add or remove a desktop launcher "
                f"that runs it from\n{APPCENTER_URL}"
            )
            needs.update("")
            return
        entry = self.ctx.catalog.find(app_id or "")
        if entry is None:
            detail.update("")
            needs.update("")
            return
        view = self.ctx.view(entry)
        status = self.ctx.status(entry)
        lines = [view.name, ""]
        if view.description:
            lines += [view.description, ""]
        lines.append(f"package:   {entry.package.requirement}")
        if view.publisher:
            lines.append(f"publisher: {view.publisher}")
        if view.homepage:
            lines.append(f"homepage:  {view.homepage}")
        latest = (
            f"{status.latest} ({view.released})"
            if view.released
            else (status.latest or "?")
        )
        lines.append(f"latest:    {latest}")
        lines.append(f"installed: {status.installed or '-'}")
        lines.append(f"launch:    {entry.command} {' '.join(entry.args)}".rstrip())
        if status.commands:
            lines.append(f"provides:  {', '.join(status.commands)}")
        if entry.is_web:
            lines.append(f"url:       {entry.launch_url}")
        if entry.data:
            lines.append(f"data:      {', '.join(entry.data)}")
        detail.update("\n".join(lines))
        needs.update("\n".join(explain_needs(entry, self.ctx)) if entry.needs else "")

    @on(DataTable.RowHighlighted)
    def _on_row_highlighted(self) -> None:
        self._render_detail()

    def _guard(self) -> bool:
        if self._busy:
            self.notify("Wait for the current action to finish.", severity="warning")
            return False
        return True

    # -- workers ----------------------------------------------------------------

    @work(thread=True, exclusive=True, group="status")
    def _refresh_status(self, announce: bool = False) -> None:
        """Re-read status in the background; ``announce`` logs when it is done.

        The explicit ``r`` key announces (it printed "Refreshing..." and the
        user is waiting for the answer); the mount-time and post-launch
        refreshes stay quiet.
        """
        failure: str | None = None
        try:
            refresh(self.ctx)
        except UvError as exc:
            failure = str(exc)
        self.call_from_thread(self._render_rows)
        if failure is not None:
            self.call_from_thread(
                self.log_line, f"Refresh failed: {failure}" if announce else failure
            )
        elif announce:
            self.call_from_thread(self.log_line, "Refreshed.")

    @work(thread=True, exclusive=True, group="uv")
    def _run_action(
        self,
        label: str,
        entries: list[AppEntry],
        action: Callable[[AppEntry, Context, LineSink], object],
    ) -> None:
        self._busy = True

        def sink(line: str) -> None:
            self.call_from_thread(self.log_line, line)

        try:
            for entry in entries:
                try:
                    action(entry, self.ctx, sink)
                except (UvError, ShortcutError) as exc:
                    sink(f"{label} failed: {exc}")
        finally:
            self._busy = False
            self.call_from_thread(self._render_rows)

    # -- actions ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self.log_line("Refreshing...")
        self._refresh_status(announce=True)

    def action_select(self) -> None:
        app_id = self._cursor_id()
        if app_id is None or app_id == APPCENTER_ROW_ID:
            return
        if app_id in self.selected:
            self.selected.remove(app_id)
        else:
            self.selected.add(app_id)
        self._render_rows()

    def action_install(self) -> None:
        if self._guard():
            self._run_action("Install", self._targets(), install_app)
            self.selected.clear()

    def action_upgrade(self) -> None:
        if self._guard():
            targets = [e for e in self._targets() if self.ctx.status(e).installed]
            self._run_action("Upgrade", targets, install_app)
            self.selected.clear()

    @work(group="modal")
    async def action_uninstall(self) -> None:
        if not self._guard():
            return
        targets = [e for e in self._targets() if self.ctx.status(e).installed]
        if not targets:
            self.notify("Nothing selected is installed.")
            return
        names = ", ".join(self.ctx.view(e).name for e in targets)
        commands = sorted({c for e in targets for c in self.ctx.status(e).commands})
        question = f"Uninstall {names}?\n\nThis removes: {', '.join(commands) or 'its commands'}.\nYour data stays in place."
        if await self.push_screen_wait(ConfirmScreen(question)):
            self._run_action("Uninstall", targets, uninstall_app)
            self.selected.clear()

    def action_launch(self) -> None:
        if not self._guard():
            return
        entry = self.ctx.catalog.find(self._cursor_id() or "")
        if entry is None:
            return
        if entry.is_web:
            self._run_action("Launch", [entry], _launch_and_report)
        else:
            with self.suspend():
                result = launch_app(entry, self.ctx, print)
                input(f"{result.message}\nPress Enter to return to the App Center.")
            self._refresh_status()

    def action_open(self) -> None:
        entry = self.ctx.catalog.find(self._cursor_id() or "")
        if entry is not None:
            open_app(entry, self.ctx, self.log_line)

    def action_close(self) -> None:
        if not self._guard():
            return
        entry = self.ctx.catalog.find(self._cursor_id() or "")
        if entry is not None:
            self._run_action("Stop", [entry], stop_app)

    def action_shortcut(self) -> None:
        if not self._guard():
            return
        app_id = self._cursor_id()
        if app_id == APPCENTER_ROW_ID:
            try:
                if appcenter_launcher_present(self.ctx):
                    remove_appcenter_shortcut(self.ctx, self.log_line)
                else:
                    add_appcenter_shortcut(self.ctx, self.log_line)
            except (ShortcutError, UvError) as exc:
                self.log_line(f"Launcher failed: {exc}")
            self._render_rows()
            return
        entry = self.ctx.catalog.find(app_id or "")
        if entry is None:
            return
        action = remove_shortcut if self.ctx.status(entry).launcher else add_shortcut
        self._run_action("Launcher", [entry], action)


def _launch_and_report(entry: AppEntry, ctx: Context, sink: LineSink) -> None:
    result = launch_app(entry, ctx, sink)
    sink(result.message)


def run_tui(ctx: Context) -> int:
    AppCenterApp(ctx).run()
    return 0


# --- main -------------------------------------------------------------------------------


def build_context(args: argparse.Namespace) -> Context:
    sources, use_default, remember = catalog_options(args)
    if remember and not sources:
        raise CatalogError("--remember needs at least one --catalog")
    path = saved_catalogs_path()
    catalog = resolve_catalog(
        sources, use_default=use_default, saved=read_saved_catalogs(path)
    )
    if remember:
        for item in save_catalogs(path, sources):
            _print(f"Saved catalog {item}; every run now loads it.")
    return Context(catalog=catalog, uv=Uv(), offline=bool(os.environ.get(OFFLINE_ENV)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            return cmd_catalog(args, fetch=_http_get)
        ctx = build_context(args)
        if args.command in (None, "ui"):
            if args.command is None and not sys.stdin.isatty():
                parser.print_help()
                return 2
            ctx.uv.require()
            return run_tui(ctx)
        return COMMANDS[args.command](args, ctx)
    except (CatalogError, UvError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
