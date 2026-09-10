"""Catalog parsing, validation, loading, and merging."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

import talkpipe_appcenter as ts
from conftest import SMALL_CATALOG


def test_embedded_catalog_parses_with_three_entries() -> None:
    catalog = ts.parse_catalog(ts.EMBEDDED_CATALOG, source="<built-in>")

    assert [e.id for e in catalog.apps] == ["vault", "writing-assistant", "talkpipe"]
    vault = catalog.find("vault")
    assert vault is not None
    assert vault.package == ts.PackageSpec("talkpipe-vault", "talkpipe-vault")
    assert vault.command == "vault-server"
    assert vault.args == ("--resume",)
    assert vault.is_web
    assert vault.port == 8002
    assert vault.health == "/api/health"
    assert vault.opens_browser
    assert vault.launch_url == "http://127.0.0.1:8002/"
    talkpipe = catalog.find("talkpipe")
    assert talkpipe is not None
    assert talkpipe.package.name == "talkpipe"
    assert talkpipe.package.requirement == "talkpipe[all]"
    assert talkpipe.health is None


def test_embedded_catalog_matches_the_repository_file() -> None:
    """The file in catalog/ is what deployers copy; it must equal the built-in."""
    on_disk = (Path(__file__).resolve().parent.parent / "talkpipe.toml").read_text()
    stripped = "\n".join(
        line for line in on_disk.splitlines() if not line.startswith("#")
    ).strip()

    assert stripped == ts.EMBEDDED_CATALOG.strip()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("talkpipe-vault", ts.PackageSpec("talkpipe-vault", "talkpipe-vault")),
        ("Talkpipe_Vault", ts.PackageSpec("talkpipe-vault", "Talkpipe_Vault")),
        ("talkpipe[all]", ts.PackageSpec("talkpipe", "talkpipe[all]")),
        (
            "talkpipe[all,dev]==1.0",
            ts.PackageSpec("talkpipe", "talkpipe[all,dev]==1.0"),
        ),
        (
            "talkpipe-vault @ /tmp/x.whl",
            ts.PackageSpec("talkpipe-vault", "/tmp/x.whl", "/tmp/x.whl"),
        ),
        (
            "tool @ git+https://example.com/r.git",
            ts.PackageSpec(
                "tool", "git+https://example.com/r.git", "git+https://example.com/r.git"
            ),
        ),
    ],
)
def test_parse_package(text: str, expected: ts.PackageSpec) -> None:
    assert ts.parse_package(text) == expected


@pytest.mark.parametrize(
    "text", ["", "@ /x.whl", "a b", "-bad", "git+https://x/y.git", "name>=1"]
)
def test_parse_package_rejects(text: str) -> None:
    with pytest.raises(ts.CatalogError):
        ts.parse_package(text)


def test_app_id_prefix() -> None:
    catalog = ts.parse_catalog(SMALL_CATALOG)
    vault = catalog.find("vault")
    assert vault is not None
    assert vault.app_id == "talkpipe-vault"
    already = dataclasses.replace(vault, id="talkpipe-x")
    assert already.app_id == "talkpipe-x"


def test_install_requirement_applies_release_pin() -> None:
    entry = ts.parse_catalog(
        'schema_version = 1\n[[apps]]\nid = "aa"\npackage = "pkg[x]"\ncommand = "a"\nrelease = "2.0"\n'
    ).apps[0]
    assert entry.install_requirement == "pkg[x]==2.0"


def _catalog_with(entry_lines: str, extra_top: str = "") -> str:
    return f'schema_version = 1\n{extra_top}[[apps]]\nid = "aa"\npackage = "pkg"\ncommand = "a"\n{entry_lines}'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not toml [", "not valid TOML"),
        (
            "schema_version = 2\n[[apps]]\nid='a'\npackage='p'\ncommand='a'\n",
            "schema_version must be 1",
        ),
        ("schema_version = 1\n", "apps must be a non-empty list"),
        ("schema_version = 1\napps = []\n", "apps must be a non-empty list"),
        (_catalog_with("", "bogus = 1\n"), "unknown top-level key(s) bogus"),
        (_catalog_with("bogus = 1\n"), "unknown key(s) bogus"),
        (
            "schema_version = 1\n[[apps]]\nid = 'aa'\ncommand = 'a'\n",
            "missing required key package",
        ),
        (_catalog_with('kind = "gui"\n'), "kind must be one of"),
        (_catalog_with('kind = "web"\n'), "a web app needs a port"),
        (_catalog_with('kind = "web"\nport = 70000\n'), "port must be between"),
        (_catalog_with('port = "80"\n'), "port must be an integer"),
        (_catalog_with('health = "health"\n'), "health must be a path"),
        (_catalog_with('args = "x"\n'), "args must be a list"),
        (_catalog_with("args = [1]\n"), "every item of args must be a string"),
        (
            _catalog_with('opens_browser = "yes"\n'),
            "opens_browser must be true or false",
        ),
        (
            _catalog_with('index = "http://example.com/simple/"\n'),
            "must be an https:// URL",
        ),
        (
            _catalog_with('release = "1"\n').replace('"pkg"', '"pkg @ /x.whl"'),
            "release cannot pin",
        ),
        (
            _catalog_with('release = "1"\n').replace('"pkg"', '"pkg==2"'),
            "give the version once",
        ),
        (
            _catalog_with("") + '[[apps]]\nid = "aa"\npackage = "q"\ncommand = "q"\n',
            "duplicate app id",
        ),
        (_catalog_with("").replace('"aa"', '"A"', 1), "must be 2-63 lowercase"),
    ],
)
def test_parse_catalog_rejects(text: str, message: str) -> None:
    with pytest.raises(ts.CatalogError, match=re.escape(message)):
        ts.parse_catalog(text, source="<t>")


def test_index_allows_http_on_localhost() -> None:
    entry = ts.parse_catalog(
        _catalog_with('index = "http://localhost:3000/simple/"\n')
    ).apps[0]
    assert entry.index == "http://localhost:3000/simple/"


def test_load_catalog_from_file_and_directory(tmp_path: Path) -> None:
    path = tmp_path / "talkpipe-appcenter.toml"
    path.write_text(SMALL_CATALOG)

    assert ts.load_catalog(str(path)).sources == (str(path),)
    assert [e.id for e in ts.load_catalog(str(tmp_path)).apps] == ["vault", "tool"]


def test_load_catalog_missing_file_is_a_catalog_error(tmp_path: Path) -> None:
    with pytest.raises(ts.CatalogError, match="could not read catalog"):
        ts.load_catalog(str(tmp_path / "nope.toml"))


def test_load_catalog_from_https_uses_the_fetcher() -> None:
    seen: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        seen.append(url)
        return SMALL_CATALOG.encode()

    catalog = ts.load_catalog("https://example.com/cat.toml", fetch=fetch)

    assert seen == ["https://example.com/cat.toml"]
    assert catalog.sources == ("https://example.com/cat.toml",)


def test_load_catalog_rejects_plain_http_and_oversize() -> None:
    with pytest.raises(ts.CatalogError, match="must be an https"):
        ts.load_catalog("http://example.com/cat.toml", fetch=lambda u, t: b"")
    with pytest.raises(ts.CatalogError, match="larger than"):
        ts.load_catalog(
            "https://example.com/cat.toml",
            fetch=lambda u, t: b"x" * (ts.MAX_CATALOG_BYTES + 1),
        )
    with pytest.raises(ts.CatalogError, match="could not fetch"):
        ts.load_catalog(
            "https://example.com/cat.toml",
            fetch=lambda u, t: (_ for _ in ()).throw(OSError("down")),
        )


def test_merge_later_entry_wins_and_sources_accumulate() -> None:
    base = ts.parse_catalog(SMALL_CATALOG, source="base")
    overlay = ts.parse_catalog(
        'schema_version = 1\nname = "Mine"\n[[apps]]\nid = "vault"\npackage = "talkpipe-vault @ /x.whl"\ncommand = "vault-server"\n'
        '[[apps]]\nid = "extra"\npackage = "extra"\ncommand = "extra"\n',
        source="overlay",
    )

    merged = ts.merge_catalogs(base, overlay)

    assert [e.id for e in merged.apps] == ["vault", "tool", "extra"]
    vault = merged.find("vault")
    assert vault is not None
    assert vault.package.is_direct
    assert merged.name == "Mine"
    assert merged.sources == ("base", "overlay")


def test_resolve_catalog_env_and_args_overlay_the_default(tmp_path: Path) -> None:
    from_env = tmp_path / "env.toml"
    from_env.write_text(
        'schema_version = 1\n[[apps]]\nid = "vault"\npackage = "talkpipe-vault==1.0.0"\ncommand = "vault-server"\n'
    )
    from_arg = tmp_path / "arg.toml"
    from_arg.write_text(
        'schema_version = 1\n[[apps]]\nid = "mine"\npackage = "mine"\ncommand = "mine"\n'
    )

    catalog = ts.resolve_catalog([str(from_arg)], env={ts.CATALOG_ENV: str(from_env)})

    assert [e.id for e in catalog.apps] == [
        "vault",
        "writing-assistant",
        "talkpipe",
        "mine",
    ]
    vault = catalog.find("vault")
    assert vault is not None
    assert vault.package.requirement == "talkpipe-vault==1.0.0"


def test_resolve_catalog_without_default_needs_a_source(tmp_path: Path) -> None:
    with pytest.raises(ts.CatalogError, match="needs at least one --catalog"):
        ts.resolve_catalog([], env={}, use_default=False)
    path = tmp_path / "c.toml"
    path.write_text(SMALL_CATALOG)
    assert [
        e.id for e in ts.resolve_catalog([str(path)], env={}, use_default=False).apps
    ] == ["vault", "tool"]


def test_saved_catalogs_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "catalogs.txt"
    assert ts.read_saved_catalogs(path) == []
    local = tmp_path / "mine.toml"
    url = "https://example.org/a.toml"

    added = ts.save_catalogs(path, [url, str(local), url])
    assert added == [url, str(local.resolve())]  # URLs as given, paths absolute
    assert ts.save_catalogs(path, [url]) == []  # already there
    assert ts.read_saved_catalogs(path) == [url, str(local.resolve())]
    assert path.read_text().startswith("#")

    assert ts.forget_catalog(path, url)
    assert not ts.forget_catalog(path, url)
    assert ts.read_saved_catalogs(path) == [str(local.resolve())]
    assert ts.forget_catalog(path, str(local))  # matched after normalisation
    assert ts.read_saved_catalogs(path) == []


def test_saved_catalogs_file_skips_comments_blank_lines_and_repeats(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalogs.txt"
    path.write_text(
        "# mine\n\n https://example.org/a.toml \nhttps://example.org/a.toml\n"
    )
    assert ts.read_saved_catalogs(path) == ["https://example.org/a.toml"]


def test_resolve_catalog_loads_saved_before_env_and_args(tmp_path: Path) -> None:
    saved = tmp_path / "saved.toml"
    saved.write_text(
        'schema_version = 1\n[[apps]]\nid = "mine"\npackage = "mine==1"\ncommand = "mine"\n'
    )
    from_arg = tmp_path / "arg.toml"
    from_arg.write_text(
        'schema_version = 1\n[[apps]]\nid = "mine"\npackage = "mine==2"\ncommand = "mine"\n'
    )

    catalog = ts.resolve_catalog([str(from_arg)], env={}, saved=[str(saved)])

    assert [e.id for e in catalog.apps] == [
        "vault",
        "writing-assistant",
        "talkpipe",
        "mine",
    ]
    mine = catalog.find("mine")
    assert mine is not None
    assert mine.package.requirement == "mine==2"  # the argument wins over the saved
    assert catalog.sources == ("<built-in>", str(saved), str(from_arg))


def test_resolve_catalog_names_a_saved_catalog_that_fails(tmp_path: Path) -> None:
    gone = tmp_path / "gone.toml"
    with pytest.raises(ts.CatalogError, match=f"catalog remove {re.escape(str(gone))}"):
        ts.resolve_catalog([], env={}, saved=[str(gone)])
    with pytest.raises(ts.CatalogError) as excinfo:
        ts.resolve_catalog([str(gone)], env={})
    assert "catalog remove" not in str(excinfo.value)  # not saved: no such hint


def test_default_config_dir_per_platform() -> None:
    assert ts.default_config_dir("linux", {"XDG_CONFIG_HOME": "/x"}) == Path(
        "/x/talkpipe-appcenter"
    )
    assert (
        ts.default_config_dir("linux", {})
        == Path.home() / ".config" / "talkpipe-appcenter"
    )
    assert ts.default_config_dir("darwin", {}) == (
        Path.home() / ".config" / "talkpipe-appcenter"
    )
    assert ts.default_config_dir("win32", {"APPDATA": "/roaming"}) == Path(
        "/roaming/talkpipe-appcenter"
    )
    assert ts.saved_catalogs_path("linux", {"XDG_CONFIG_HOME": "/x"}) == Path(
        "/x/talkpipe-appcenter/catalogs.txt"
    )
