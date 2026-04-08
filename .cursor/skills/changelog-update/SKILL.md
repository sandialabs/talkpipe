---
name: changelog-update
description: Update CHANGELOG.md following TalkPipe conventions. Use after implementing a feature, fixing a bug, or making any user-facing change. Ensures correct "update vs add" logic and entry format.
---

# Update Changelog

Updates [CHANGELOG.md](CHANGELOG.md) under the `## Unreleased` section following project conventions.

## When to Use

- After implementing a new feature
- After fixing a bug
- After any user-facing change (docs, config, behavior)

## Decision Flow

1. **Is this a minor change to an existing feature already mentioned in Unreleased?**
   - Yes → Update that existing bullet; do not add a new one
   - No → Add a new bullet under Unreleased

2. **Is this purely internal/refactor with no user impact?**
   - Yes → Changelog update optional; add only if it clarifies a release
   - No → Always update

## Format Rules

- **Style**: Present tense, sentence case
- **Structure**: One bullet per logical change; multi-line bullets use 2-space indent for continuation
- **Placement**: New entries go at the top of the Unreleased list (after the `## Unreleased` heading)
- **Commands/APIs**: Use backticks for names (e.g. `makevectordatabase`, `run_doc_examples`)
- **Links**: Use `[text](path)` for doc references when helpful

## Examples

**New feature (add new bullet):**
```markdown
- Added **mySegment** for filtering items by score threshold.
```

**Minor change to existing feature (update existing bullet):**
If Unreleased already has:
```markdown
- Doc examples tests clean up artifacts (e.g. `my_knowledge_base` from RAG examples) after each test.
```
And you add validation for path traversal, update it:
```markdown
- Doc examples tests clean up artifacts (e.g. `my_knowledge_base` from RAG examples) after each test.
  Cleanup validates paths before deletion to prevent path traversal.
```

**Bug fix:**
```markdown
- Fixed chatterlang_serve stream interface so search results display reliably.
```

**Multiple related changes (one bullet):**
```markdown
- RAG source citation: ProcessDocumentsSegment preserves title and source (path) as separate
  metadata fields; construct_background prioritizes them in prompts; default system prompt and
  prompt_directive instruct the LLM to cite sources.
```

## Checklist

- [ ] Check Unreleased for an existing entry that covers this change
- [ ] Update that entry if found; otherwise add a new bullet
- [ ] Use present tense
- [ ] Place new bullets at the top of the Unreleased list
