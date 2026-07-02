---
mode: agent
description: Follow TalkPipe TDD workflow. Use when implementing features, fixing bugs, or adding segments/sources. Enforces write-fail-fix-pass order.
---

Follow the TalkPipe TDD workflow for this change:

1. **Write or update a test** in `tests/` that fails without the change. Prefer updating an existing test file over creating a new one.
2. **Verify the test fails**: run `source .venv/bin/activate && pytest <test-file> -v`
3. **Implement the change**
4. **Verify the test passes**: re-run the same pytest command

Constraints:
- Tests mirror `src/` structure under `tests/talkpipe/`
- Keep tests as short as possible while covering the functionality completely
- Use `pytest.fixture` and `pytest-mock` for dependencies
- Always use the `.venv` environment; abort and alert if it doesn't exist

If a unit test is not reasonable (e.g., requires external LLM, is purely cosmetic), notify the user and explain why.

The change to implement: $input
