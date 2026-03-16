---
name: test-driven-development
description: Follow TalkPipe TDD workflow when making code changes. Use when implementing features, fixing bugs, or refactoring. Enforces write-fail-fix-pass order and test placement conventions.
---

# Test-Driven Development

Follow the project TDD workflow when making code changes. Tests live under `tests/`; use `.venv` for running them.

## When to Use

- Implementing a new feature
- Fixing a bug
- Refactoring code that should have test coverage

## Workflow (Strict Order)

1. **Write a unit test** that fails without the change (or update an existing test)
2. **Verify the test fails**: `pytest tests/... -v` (or the specific test)
3. **Make the code change**
4. **Verify the test passes**: `pytest tests/... -v` or `pytest --cov=src`

## Conventions

- **Location**: Unit tests under `tests/`
- **Prefer**: Update and augment existing tests over creating new ones
- **Scope**: Tests should be as short as possible while testing functionality completely
- **Environment**: Use `.venv`; activate with `source .venv/bin/activate` or run via `.venv/bin/python`

## Commands

```bash
# Run all tests with coverage
pytest --cov=src

# Run a specific test file
pytest tests/test_foo.py -v

# Run a specific test
pytest tests/test_foo.py::test_bar -v
```

## When a Test Is Not Reasonable

Notify the user if it is not reasonable to write a unit test. Examples:

- One-off scripts or exploratory code
- Changes that are purely cosmetic or documentation-only
- Integration tests that require external services not available in CI
- Code paths that are unreachable or deprecated

Do not skip the test silently; explain why and get user confirmation.

## Checklist

- [ ] Test written or existing test updated
- [ ] Test fails before the change (verified)
- [ ] Code change made
- [ ] Test passes after the change (verified)
- [ ] If no test: user notified with reason
