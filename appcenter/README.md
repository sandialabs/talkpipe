# TalkPipe App Center

> Install, launch, and manage applications from one screen, with nothing to
> set up first but [uv](https://docs.astral.sh/uv/).

The App Center is the part of TalkPipe that installs applications. It is
designed to make the TalkPipe-based applications (the vault, the writing
assistant, the workbench) easy to install, upgrade, and launch, and it comes
with a catalog of them. It is just as easy to use for **any Python
application that pip can install and that has a command of its own**: the
catalog is a small text file, and one line in it lists any other package on
PyPI or a private index. Installing, upgrading, launching, and adding a
desktop launcher then work the same for that package as for TalkPipe's own.
Nothing in the application has to know the App Center exists.

The App Center is itself a single Python file. uv runs it straight from its
URL, fetching the Python and the one library it needs into a cached
environment:

```bash
uv run https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py
```

Don't have uv? One command installs it and then opens the App Center:

```bash
# Linux / macOS
curl -fsSL https://github.com/sandialabs/talkpipe/releases/latest/download/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -c "irm https://github.com/sandialabs/talkpipe/releases/latest/download/install.ps1 | iex"
```

You get an app-store-like screen: every application in the catalog with its
installed and latest versions, whether it is running, and whether it has a
desktop launcher. Keys:

| Key | Action |
|---|---|
| `i` | Install (or upgrade) the app under the cursor, or every selected app |
| `u` | Upgrade only apps that are installed |
| `x` | Uninstall (asks first; your data stays) |
| `l` | Launch. Web apps start in the background and open in your browser |
| `o` | Open a running web app in the browser |
| `s` | Add or remove a desktop launcher (menu entry, `~/Applications`, or Start Menu) |
| `c` | Stop a web app the App Center started |
| `space` | Select for a batch install |
| `r` | Refresh |
| `q` | Quit |

The last row is the App Center itself: press `s` there to give the App Center a launcher
of its own, so nobody has to type a URL twice.

## Without the screen

Every action is also a subcommand, for scripts and for people who prefer
typing. Arguments after `sh -s --` pass straight through the bootstrap script.

```bash
uv run <url> list                  # every app and its status (--json for machines)
uv run <url> info vault
uv run <url> install vault writing-assistant
uv run <url> upgrade --all
uv run <url> launch vault
uv run <url> stop vault
uv run <url> shortcut add vault    # or: shortcut remove vault; shortcut add appcenter
uv run <url> uninstall vault       # -y to skip the question
uv run <url> install myapp --catalog https://example.org/apps.toml --remember
                                   # from a catalog of your own, kept for later runs
uv run <url> catalog list          # the saved catalogs; also: catalog add, catalog remove

curl -fsSL .../install.sh | sh -s -- install vault
```

## What it does, and does not do

- **Applications install with `uv tool install`**, each into its own
  environment with its own Python. Nothing else on the computer is touched,
  and uninstalling removes exactly that environment and its commands. User
  data (the vault's `~/.talkpipe-vault`, the writing assistant's
  `~/.writing_assistant`) is never deleted; the App Center tells you where it is.
- **Re-running an install upgrades.** "Latest" is read from PyPI every time
  the App Center starts, so the screen always knows whether an upgrade exists.
- **Launchers open a visible terminal** on purpose: the applications have no
  tray icon or Quit command, so that window is how you stop them and see
  their messages. The launcher targets the stable `~/.local/bin` command, so
  it survives upgrades.
- **Language models are not installed.** The catalog says which apps need
  Ollama; the App Center detects it and shows the download link, or you enter an
  OpenAI or Anthropic key in the app's own settings.
- **The App Center needs the network** to start (uv fetches the file) and to show
  latest versions. Set `TALKPIPE_APPCENTER_OFFLINE=1` to skip the PyPI lookups;
  versions then show as `?`.

uv is the only prerequisite. It must be at least 0.7.

## The catalog: listing any pip-installable application

The App Center is driven by a small TOML catalog. The built-in one lists the
TalkPipe applications; it is also the file [`talkpipe.toml`](talkpipe.toml)
next to this README, which doubles as the authoring reference. To offer your
own application, or any other package that installs a console script, add an
entry like the ones below and point the App Center at your catalog
(next section). The minimum is three lines: an `id`, the `package` name, and
the `command` to run.

Most of what the screen shows is **not** in the catalog. For every entry the
App Center asks PyPI for the summary, publisher, homepage, latest version and its
date, so a catalog does not go stale when the software it lists releases.
Which commands a package installs is read from the installed environment. The
catalog carries only what PyPI cannot know:

```toml
schema_version = 1
name = "My apps"

[[apps]]
id = "vault"                      # required; lowercase letters, digits, hyphens
name = "TalkPipe Vault"           # optional; PyPI's name is the distribution name
package = "talkpipe-vault"        # required; "name", "name[extra]", "name==1.2",
                                  #   or "name @ https://…/x.whl" (or a local path)
command = "vault-server"          # required; the console script to launch
args = ["--resume"]
kind = "web"                      # web | cli | tui (default cli)
port = 8002                       # web only
health = "/api/health"            # optional; else /health, /api/health, then TCP
opens_browser = true              # the app opens its own tab; the App Center won't
icon = "talkpipe_vault/apps/static/icon-256.png"   # a PNG inside the package
data = ["~/.talkpipe-vault"]      # shown on uninstall, never deleted
needs = ["ollama"]                # detected and explained, never installed
# index = "https://pypi.example.org/simple/"   # a private index (--index)
# release = "1.0.0"               # a deliberate pin; leave unset to track latest
```

Any package on PyPI (or a private index) that installs a console script can
be listed, whether or not it has anything to do with TalkPipe. It does not
need to know the App Center exists; `kind`, `port`, and the rest just make
the App Center's status and launch actions smarter for it. A minimal entry:

```toml
[[apps]]
id = "ruff"
package = "ruff"
command = "ruff"
```

### Your own catalog

Point the App Center at a catalog with `--catalog <https-url-or-path>`
(repeatable, before or after the subcommand) or the
`TALKPIPE_APPCENTER_CATALOG` environment variable (several, separated by `:`
on Unix and `;` on Windows). Either applies to that run only. To keep a
catalog without typing it every time, add `--remember` to any command, or
save it on its own:

```bash
uv run <url> install myapp --catalog https://example.org/apps.toml --remember
uv run <url> catalog add https://example.org/apps.toml   # the same, installing nothing
uv run <url> catalog list
uv run <url> catalog remove https://example.org/apps.toml
```

Saved catalogs are loaded on every run, screen or subcommand. They live in a
plain text file, one URL or path per line (local paths are saved absolute):
`~/.config/talkpipe-appcenter/catalogs.txt` on Linux and macOS
(`XDG_CONFIG_HOME` is honoured), `%APPDATA%\talkpipe-appcenter\catalogs.txt`
on Windows. A catalog is loaded before it is saved, so a typo is not kept;
if a saved one later stops loading, the error names it and `catalog remove`
takes it out.

Catalogs overlay the built-in one in the order saved, environment variable,
`--catalog`, later entries winning by `id`, so you can override one field of
a built-in app (point `vault` at an internal index, say) or ship a whole
catalog of your own. `--no-default-catalog` drops the built-in list for that
run (it is never saved). Unknown or mistyped keys are errors, not warnings,
so a typo cannot silently drop metadata. Catalog URLs must be `https://`;
plain `http://` is accepted only for `localhost`.

## Reproducibility and trust

`uv run <url>` executes what it downloads, the same trust model as
`curl | sh`. The `releases/latest/download/` URL always points at the newest
talkpipe release. For a copy that never changes, use a release tag instead:

```
https://github.com/sandialabs/talkpipe/releases/download/v1.1.0/talkpipe_appcenter.py
```

The file is written to be read; it has no dependency but Textual and no build
step. Run it with `--version` to see which talkpipe release it shipped with (a
copy taken from the `main` branch reports `0.0.0+unknown`, meaning
"development copy").

## Development

The App Center is a part of TalkPipe that lives outside the `talkpipe` Python
package: `pip install talkpipe` does not include it, and it imports nothing
from it. In the repository it is `appcenter/`: this file, the catalog, the two
bootstrap scripts, and `tests/`. `talkpipe_appcenter.py` is the whole of it
and must keep running from a plain interpreter that has only Textual
installed. From the talkpipe checkout:

```bash
uv sync --all-extras                 # Textual and pytest-asyncio are in the dev extra
uv run pytest appcenter/tests            # the App Center's suite (fake uv, fake PyPI, Textual Pilot)
uv run ruff check appcenter && uv run mypy   # talkpipe's gates cover the App Center too
uv run appcenter/talkpipe_appcenter.py list  # the script form, live against PyPI
```

To try it by hand without touching your real home:

```bash
S=$(mktemp -d ~/.cache/appcenter-XXXX)
HOME=$S XDG_DATA_HOME=$S/share XDG_STATE_HOME=$S/state \
  UV_TOOL_DIR=$S/tools UV_TOOL_BIN_DIR=$S/bin \
  uv run appcenter/talkpipe_appcenter.py
```

The tests never run the real uv or touch the network: `tests/conftest.py`
writes a fake `uv` onto `PATH` that answers in real uv's output format, and a
dict-backed PyPI. Every external touchpoint of the file (uv, HTTP, the
launcher's helper commands, the home directory, the platform) is injectable
for that reason; keep it so. Versions come from talkpipe's git tags: the
release workflow stamps the tag into `STAMPED_VERSION` before attaching the
file to the GitHub release, so never edit that line by hand.
