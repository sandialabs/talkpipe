---
mode: agent
description: Update CHANGELOG.md after implementing a feature, fixing a bug, or making any user-facing change. Handles update-vs-add logic correctly.
---

Update [CHANGELOG.md](../../CHANGELOG.md) under the `## Unreleased` section.

**Decision logic:**
1. Is this a **minor change to an existing feature** already mentioned in Unreleased?
   - Yes → Update that existing bullet; do not add a new one
   - No → Add a new bullet at the top of the Unreleased list

2. Is this **purely internal** (refactor, no user impact)?
   - Yes → Changelog update optional
   - No → Always update

**Format rules:**
- Present tense, sentence case
- Use backticks for segment/command names (e.g. `mySegment`, `run_doc_examples`)
- Link to docs with `[text](path)` when helpful
- Multi-line bullets use 2-space indent for continuation lines

The change to document: $input
