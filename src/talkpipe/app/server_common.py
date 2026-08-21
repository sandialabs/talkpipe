"""Pieces shared by TalkPipe's HTTP applications.

``chatterlang_serve`` (and ``serverag`` on top of it) and
``chatterlang_workbench`` each run a FastAPI app that compiles and runs
ChatterLang for a browser. What they have in common lives here so the two
cannot drift apart: the static asset directory, the common command-line
arguments, API-key comparison, and the compile-and-run plumbing.
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from talkpipe.util.config import add_config_values, load_module_file, parse_unknown_args

#: Browser assets shipped with the package (``talkpipe/app/static``).
STATIC_DIR = Path(__file__).parent / "static"


def mount_static(app: FastAPI) -> None:
    """Serve :data:`STATIC_DIR` at ``/static``."""
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- Command line -------------------------------------------------------------


def add_host_port_args(
    parser: argparse.ArgumentParser, *, default_host: str, default_port: int
) -> None:
    """Add ``-o/--host`` and ``-p/--port``."""
    parser.add_argument(
        "-o",
        "--host",
        default=default_host,
        help=f"Host to bind to (default: {default_host})",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=default_port,
        help=f"Port to listen on (default: {default_port})",
    )


def add_load_module_arg(parser: argparse.ArgumentParser) -> None:
    """Add the repeatable ``--load-module`` option."""
    parser.add_argument(
        "--load-module",
        action="append",
        default=[],
        type=str,
        help="Path to a custom module file to import before running the script.",
    )


def apply_cli_constants(unknown_args: list[str]) -> dict[str, Any]:
    """Turn leftover ``--key value`` arguments into configuration values.

    They become reachable from scripts as ``$key``. Returns what was added.
    """
    constants = parse_unknown_args(unknown_args)
    if constants:
        add_config_values(constants, override=True)
        print(f"Added command-line values to configuration: {list(constants.keys())}")
    return constants


def load_module_files_or_exit(module_files: Iterable[str]) -> None:
    """Import each ``--load-module`` file, exiting with a clear message if one is missing."""
    for module_file in module_files:
        try:
            load_module_file(fname=module_file, fail_on_missing=True)
        except FileNotFoundError as exc:
            print(
                f"ERROR: {exc}. Relative paths are resolved against the current "
                f"directory; run the command from the directory containing the "
                f"module or pass an absolute path.",
                file=sys.stderr,
            )
            sys.exit(1)


def is_loopback_host(host: str) -> bool:
    """True if ``host`` only ever resolves to this machine (127/8, ::1, localhost)."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# --- Authentication -----------------------------------------------------------


def api_key_matches(supplied: str | None, expected: str | None) -> bool:
    """Constant-time comparison of a client's ``X-API-Key`` with the configured key.

    Missing values never match, so a server with no key configured cannot be
    satisfied by a client that sends none.
    """
    if supplied is None or expected is None:
        return False
    return hmac.compare_digest(supplied, expected)


# --- Compile and run ----------------------------------------------------------


def is_interactive_script(script: str) -> bool:
    """A script whose first statement starts with ``|`` takes its input per request."""
    for line in script.splitlines():
        line = line.strip()
        if not line or line.startswith(("CONST", "#")):
            continue
        return line[0] == "|"
    return False


def is_output_stream(result: Any) -> bool:
    """True if a processor returned a stream of items rather than one value.

    Strings, bytes and dicts are iterable but are single results.
    """
    return hasattr(result, "__iter__") and not isinstance(result, (str, bytes, dict))


def iter_output_text(items: Iterable[Any]) -> Iterator[str]:
    """Render pipeline output items as text, one string per item.

    Pydantic models are rendered as JSON; everything else with ``str``.
    """
    for item in items:
        if hasattr(item, "model_dump_json"):
            yield item.model_dump_json()
        else:
            yield str(item)
