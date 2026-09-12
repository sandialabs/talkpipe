## Dev environment tips
- When running code or pytest, use the .venv environment in the root of the project. Activate it with `source .venv/bin/activate` (or `source .venv/Scripts/activate` on Windows).
- If the .venv environment doesn't exist and you need to run code or tests, abort and ask the user to create the environment.
- Local development resolves against the committed `uv.lock` (`uv sync --all-extras`); CI installs with pip and ignores the lock on purpose, so it resolves the way `pip install talkpipe` does. See "Development environment" in [README.md](README.md). The lock is a dev convenience, not a security control — fix a vulnerable dependency by raising its floor in [pyproject.toml](pyproject.toml), and re-run `uv lock` after any dependency change so `uv lock --check` stays green in CI.

## Important Commands
- `python -m build` — create a new release
- `pytest --cov=src` — run unit tests with coverage
- `ruff check .`, `ruff format --check .`, `mypy` — the code-quality gate. **CI fails on any finding from these three**; run them before pushing. `ruff check --fix . && ruff format .` fixes most lint/format findings; the rule set and mypy config live in `pyproject.toml`. `pre-commit install` (opt-in, per clone) runs the same checks on every commit.
- `python .cursor/skills/update-entry-points/scripts/update_entry_points.py` — generate entry points from decorators and update pyproject.toml (preferred over chatterlang_generate_entry_points when updating pyproject.toml)
- `pytest tests/test_doc_examples.py -v` — run all doc examples as tests (requires full_network for LLM examples; skip with `-m "not requires_ollama"` when Ollama unavailable)
- `run_doc_examples` — extract and run all doc examples (alternative to pytest; requires full_network for LLM examples)

## Project Overview
TalkPipe is a Python toolkit for creating, testing, and deploying workflows that integrate Generative AI with your existing tools and data sources. It treats LLMs as one tool among many, so solutions combine AI with data processing, file handling, and more.

- **Chat with LLMs** - Create multi-turn conversations with OpenAI, Ollama, or Anthropic models in just 2 lines of code
- **Process Documents** - Extract text from PDFs, analyze research papers, score content relevance
- **Analyze Web Content** - Download web pages (respecting robots.txt), extract readable text, and summarize
- **Build Data Pipelines** - Chain together data transformations, filtering, and analysis with Unix-like simplicity
- **Create AI Agents** - Build agents that can debate topics, evaluate streams of documents, or monitor RSS feeds
- **Deploy Anywhere** - Run in Jupyter notebooks, as Docker containers, or as standalone Python applications

## Project Structure
- talkpipe/app - contains runnable applications
- talkpipe/chatterlang - contains definitions for the chatterlang external DSL built on top of talkpipe/pipe
- talkpipe/data - contains basic data manipulation utilities
- talkpipe/llm - contains chat and embedding utilities
- talkpipe/operations - contains basic operations for chatterlang
- talkpipe/pipe - contains a mix of basic definitions creating the internal DSL
- talkpipe/search - contains data storage and retrieval definitions, including vector databases and full text search
- talkpipe/util - contains utility functions such as configuration and operations system related operations

## Development Guidelines 
- Do not automatically agree.  Question assumptions and point out weaknesses in logic or inconsistences with the rest of the codebase.
- pytest unit tests are under tests/
- the code for the library is under src/
- The core pipe API classes and code is under talkpipe/pipe
- ChatterLang is an external DSL and is defined under talkpipe/chatterlang
- Other packages in the project other than util include implementations of pipe sources and segments
- Util contains various generally usable utility functions, especially for basic data manipulation and configuration.
- [README.md](README.md) contains a longer overview
- After implementing a new feature, update [CHANGELOG.md](CHANGELOG.md). Check if an existing entry should be updated rather than creating a new entry. 
- After making a minor change to an existing feature,  check if the unreleased section of the changelog already mentions the feature. If so, update that changelog entry.  If not, write a new entry in the changelog.
- When making a change, write a unit test that fails without the change or update an existing test, verify that the unit test fails, make the change and then verify that the unit test now passes.  Notify the user if it is not reasonable to write the unit test. 
- When writing unit tests, update and augment existing unit tests when possible and appropriate rather than writing new unit tests.
- Unit tests should be as short as possible while still testing the functionality as completely as possible.
- User interfaces should be visually appealing and maintain consistency with each other.
- When writing or updating pipeline examples in documentation, write examples with stand-alone code and 
    test the examples by running them. Prefer unindented \`\`\`python fences for easier extraction; see 
    [docs/architecture/documentation-formatting.md](docs/architecture/documentation-formatting.md).
- When creating a new source or segment, add it to the talkpipe.sources or talkpipe.segments entry points in [pyproject.toml](pyproject.toml). Use the update-entry-points skill to generate and apply entry points automatically: `.venv/bin/python .cursor/skills/update-entry-points/scripts/update_entry_points.py`. See [docs/architecture/protocol.md](docs/architecture/protocol.md) for protocol conventions.
- When writing documentation for segments or sources, do not document the parameters.
- When writing new sources or segments, use Annotated in the parameter lists to explain the type and purpose of each parameter.

## The TalkPipe App Center (appcenter/)
- `appcenter/talkpipe_appcenter.py` is a single file users run with `uv run <url>`; it is **not** part of the `talkpipe` package and has one dependency, Textual (dev extra only, capped at its major). Do not split it into a package, add a dependency, or import talkpipe from it.
- Every external touchpoint (uv, HTTP, the launcher's helper commands, home directory, platform) is injectable; `appcenter/tests/` never runs the real uv or touches the network (see the fake uv in `appcenter/tests/conftest.py`).
- Applications need no awareness of the App Center; never ask an app to change for the App Center's sake. The catalog (`appcenter/talkpipe.toml`, embedded in the file, a test checks they match) carries only what PyPI cannot supply: launch command, port, health path, icon, data dirs, external services.
- The file reports the talkpipe release it shipped with: CI stamps the tag into `STAMPED_VERSION` on release; never edit that line by hand. `appcenter/README.md` is its user documentation.
- Two delivery channels, because `releases/latest` skips pre-releases: the stable assets, and a rolling `experimental` release CI refreshes on every release (a fixed anchor tag — its assets move, its commit does not, and the release jobs ignore any tag not starting with `v`). Which copy you run and which versions it installs are **independent**: the channel for installs comes from `--experimental` / `TALKPIPE_APPCENTER_CHANNEL`, never from this file's own version, and is recorded per application so a later `uv tool install --upgrade` cannot replace a pre-release with the newest release.
