"""LLM-driven next-segment suggestions for the workbench.

Model/source resolution follows the workbench-specific hierarchy, falling
back to the same defaults ``llmPrompt`` uses:

1. workspace ``settings.json`` (set from the workbench settings UI)
2. ``TALKPIPE_workbench_suggest_source`` / ``_model`` (CLI flags / env)
3. ``TALKPIPE_default_model_name`` / ``_source`` (standard TalkPipe config)

The adapter is used statelessly via ``complete_text_without_context``; the
model is asked for a small JSON array, and any suggested segment name that
is not actually registered gets dropped (hallucination filter).
"""

import json
import logging
import re
import time
from typing import List, Optional

from talkpipe.chatterlang import registry
from talkpipe.llm.config import getPromptAdapter, getPromptSources
from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_MODEL_NAME, TALKPIPE_SOURCE

logger = logging.getLogger(__name__)

SYNTAX_CRIB = """\
ChatterLang syntax crib:
- A pipeline is stages joined by `|`; pipelines are separated by `;`.
- Pipelines start with `INPUT FROM <source>[params]` (or `NEW <source>`), or with `|` to read user input.
- Segments transform items: `segmentName[param="value", other=3]`.
- `@name` stores/reads a variable; `CONST name = value` defines a constant; `LOOP n TIMES { ... }` repeats.
"""


def _truthy(value, default=True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in ("false", "0", "no", "off", "")


def resolve_llm_status(settings: Optional[dict] = None):
    """Resolve the suggestion LLM.

    Returns ``((source, model), None)`` on success, or ``(None, reason)``
    with a human-readable reason when no usable LLM is configured.
    """
    settings = settings or {}
    cfg = get_config()
    if not _truthy(cfg.get("workbench_llm_suggestions"), default=True):
        return None, "LLM suggestions disabled (--no-llm-suggestions)"
    source = (
        settings.get("suggest_source")
        or cfg.get("workbench_suggest_source")
        or cfg.get(TALKPIPE_SOURCE)
    )
    model = (
        settings.get("suggest_model")
        or cfg.get("workbench_suggest_model")
        or cfg.get(TALKPIPE_MODEL_NAME)
    )
    if not source or not model:
        return None, "no model configured"
    if source not in getPromptSources():
        logger.warning(f"Unknown suggestion LLM source: {source}")
        known = ", ".join(getPromptSources())
        return None, f"unknown LLM source '{source}' (known sources: {known})"
    return (source, model), None


def resolve_llm(settings: Optional[dict] = None):
    """Resolve (source, model) for suggestions, or None if unavailable."""
    resolved, _ = resolve_llm_status(settings)
    return resolved


def unreachable_reason(source: str, model: str) -> str:
    """An actionable message for a configured-but-unreachable model."""
    # A missing or broken provider dependency surfaces as an ImportError from
    # the adapter's is_available() (e.g. "Ollama is not installed. Please install
    # it with: pip install talkpipe[ollama]"). That is a different problem than
    # connectivity — and its message already tells the user exactly what to do —
    # so surface it verbatim instead of the misleading "not reachable" text, which
    # would send them chasing TALKPIPE_OLLAMA_SERVER_URL / `ollama pull`.
    cause = _availability_cause.get((source, model))
    if isinstance(cause, ImportError):
        return str(cause)
    if source == "ollama":
        from talkpipe.util.constants import OLLAMA_SERVER_URL
        url = get_config().get(OLLAMA_SERVER_URL) or "http://localhost:11434"
        return (
            f"model '{model}' not reachable at {url} — if your Ollama server "
            "runs on another host, set TALKPIPE_OLLAMA_SERVER_URL and restart "
            "the workbench"
        )
    return f"model '{model}' not reachable via {source} (check credentials and connectivity)"


_availability_cache = {}
# Records the exception (if any) from the most recent failed availability check,
# so unreachable_reason can distinguish a missing dependency from a connectivity
# problem. Kept in step with _availability_cache.
_availability_cause = {}
AVAILABILITY_TTL_SECONDS = 60


def check_availability(source: str, model: str) -> bool:
    """Whether the adapter reports itself available (cached ~60s)."""
    key = (source, model)
    cached = _availability_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[1] < AVAILABILITY_TTL_SECONDS:
        return cached[0]
    cause = None
    try:
        adapter = getPromptAdapter(source)(model=model)
        available = bool(adapter.is_available())
    except Exception as e:
        logger.info(f"Suggestion LLM unavailable ({source}/{model}): {e}")
        available = False
        cause = e
    _availability_cache[key] = (available, now)
    _availability_cause[key] = cause
    return available


def invalidate_availability_cache():
    _availability_cache.clear()
    _availability_cause.clear()


def _registered_names() -> set:
    return set(registry.input_registry.available_names) | set(
        registry.segment_registry.available_names
    )


# ---------------------------------------------------------------------------
# Cursor-position grammar
#
# The same classification the editor uses for autocomplete, applied server
# side so the LLM can be told what is grammatically valid at the cursor and
# its answers can be filtered/inserted accordingly.

_KEYWORDS = {"INPUT", "FROM", "NEW", "CONST", "SET", "LOOP", "TIMES"}


def _strip_comments(text: str) -> str:
    return "\n".join(
        line[:line.index("#")] if "#" in line else line
        for line in text.split("\n")
    )


def _previous_component(stmt: str) -> Optional[str]:
    no_brackets = re.sub(r"\[[^\]]*\]?", "", stmt)
    stages = no_brackets.split("|")
    for stage in reversed(stages):
        match = re.search(r"([A-Za-z_]\w*)\s*$", stage.strip())
        if match and match.group(1) not in _KEYWORDS:
            return match.group(1)
    return None


def classify_cursor(script: str, cursor_offset: int) -> dict:
    """Grammatical position of the cursor within its statement.

    Returns ``{"context", "enclosing", "prev"}`` where context is one of:

    - ``"brackets"``: inside a component's ``[...]`` (enclosing = its name)
    - ``"source_position"``: right after ``INPUT FROM`` / ``NEW``
    - ``"pipe_stage"``: right after a ``|`` (prev = preceding component)
    - ``"after_stage"``: after a complete stage, no trailing pipe yet
    - ``"statement_start"``: an empty statement (start of script or after ;)
    """
    cursor_offset = max(0, min(cursor_offset, len(script)))
    stmt = _strip_comments(script[:cursor_offset]).split(";")[-1]
    # Drop any partial word the user is mid-typing at the cursor.
    stmt = re.sub(r"[@\w]*$", "", stmt)

    depth = 0
    bracket_idx = -1
    for i, ch in enumerate(stmt):
        if ch == "[":
            depth += 1
            if depth == 1:
                bracket_idx = i
        elif ch == "]":
            if depth > 0:
                depth -= 1
            if depth == 0:
                bracket_idx = -1
    if depth > 0:
        match = re.search(r"([A-Za-z_]\w*)\s*$", stmt[:bracket_idx])
        return {"context": "brackets",
                "enclosing": match.group(1) if match else None,
                "prev": None}

    if re.search(r"(?:INPUT\s+FROM|NEW(?:\s+FROM)?)\s*$", stmt, re.IGNORECASE):
        return {"context": "source_position", "enclosing": None, "prev": None}

    if re.search(r"\|\s*$", stmt):
        return {"context": "pipe_stage", "enclosing": None,
                "prev": _previous_component(stmt)}

    if stmt.strip():
        return {"context": "after_stage", "enclosing": None,
                "prev": _previous_component(stmt)}

    return {"context": "statement_start", "enclosing": None, "prev": None}


_CONTEXT_INSTRUCTIONS = {
    "brackets": ('The cursor is inside the parameter brackets of \'{enclosing}\'. '
                 'Every suggestion must have "segment" set to "{enclosing}" and '
                 'params_hint set to parameter assignments for it, using only its '
                 'documented parameter names.'),
    "source_position": ("The cursor is right after INPUT FROM, so only SOURCES are "
                        "valid here — never suggest a segment."),
    "pipe_stage": ("The cursor is at the start of a new pipe stage, so only "
                   "SEGMENTS are valid here — never suggest a source."),
    "after_stage": ("The cursor is after a complete stage; the next thing will be "
                    "piped, so only SEGMENTS are valid — never suggest a source."),
    "statement_start": ("The cursor is at the start of a new pipeline. It must begin "
                        "either with `INPUT FROM <source>` or with `| <segment>` "
                        "(to read interactive user input)."),
}


def _valid_types_for(context: str) -> set:
    if context == "source_position":
        return {"source"}
    if context in ("pipe_stage", "after_stage"):
        return {"segment"}
    return {"source", "segment"}


def _component_type_of(name: str) -> Optional[str]:
    if name in registry.segment_registry.available_names:
        return "segment"
    if name in registry.input_registry.available_names:
        return "source"
    return None


def insert_text_for(context_info: dict, name: str, params_hint: str,
                    comp_type: Optional[str]) -> str:
    """The exact text to insert at the cursor for a suggestion."""
    params = f"[{params_hint}]" if params_hint else ""
    context = context_info["context"]
    if context == "brackets":
        return params_hint or ""
    if context == "source_position":
        return f"{name}{params}"
    if context == "after_stage":
        return f" | {name}{params}"
    if context == "statement_start" and comp_type == "source":
        return f"INPUT FROM {name}{params}"
    if context == "statement_start":
        return f"| {name}{params}"
    return f"{name}{params}"  # pipe_stage


def _component_lines(reference: dict) -> str:
    lines = []
    for comp in reference["components"]:
        if comp.get("error"):
            continue
        summary = comp.get("summary") or ""
        lines.append(f"- {comp['name']} ({comp['type']}): {summary}"[:160])
    return "\n".join(lines)


_builtin_records_cache = None


def builtin_pipeline_records() -> List[dict]:
    """The built-in examples and seed scripts as pipeline records.

    Used as few-shot material when the user's workspace is empty or has
    nothing similar to the current script (the cold-start case).
    """
    global _builtin_records_cache
    if _builtin_records_cache is not None:
        return _builtin_records_cache
    from talkpipe.app.chatterlang_workbench import EXAMPLE_SCRIPTS
    from talkpipe.app.workbench.corpus import SEED_SCRIPTS_DIR

    records = []
    for examples in EXAMPLE_SCRIPTS.values():
        for example in examples:
            records.append({
                "name": example["name"],
                "description": example.get("description", ""),
                "script": example["code"],
            })
    if SEED_SCRIPTS_DIR.is_dir():
        for path in sorted(SEED_SCRIPTS_DIR.glob("*.script")):
            records.append({
                "name": path.stem.replace("__", ": ").replace("_", " "),
                "description": "built-in tutorial script",
                "script": path.read_text(encoding="utf-8"),
            })
    _builtin_records_cache = records
    return records


def _rank_by_similarity(current: set, records: List[dict],
                        limit: int) -> List[dict]:
    from talkpipe.app.workbench.corpus import mine_script

    scored = []
    for record in records:
        other = {name for chain in mine_script(record.get("script", ""))
                 for name in chain}
        if not other:
            continue
        score = (len(current & other) / len(current | other)) if current else 0
        scored.append((score, record))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if current:
        scored = [pair for pair in scored if pair[0] > 0] or scored
    return [record for _, record in scored[:limit]]


def _similar_pipelines(script: str, saved: List[dict], limit: int = 3):
    """(user_matches, builtin_fill): few-shot pipelines for the prompt.

    The user's own saved pipelines rank first (Jaccard similarity of
    component-name sets); when they yield fewer than ``limit``, the built-in
    examples/seeds fill the remaining slots so the model always sees complete,
    well-formed ChatterLang even on a fresh workspace.
    """
    from talkpipe.app.workbench.corpus import mine_script

    current = {name for chain in mine_script(script) for name in chain}
    user_matches = _rank_by_similarity(current, saved, limit)
    builtin_fill = []
    if len(user_matches) < limit:
        builtin_fill = _rank_by_similarity(
            current, builtin_pipeline_records(), limit - len(user_matches)
        )
    return user_matches, builtin_fill


def _signature_line(comp: dict) -> str:
    """A compact full signature for one component."""
    params = "; ".join(
        f"{p['name']}: {p.get('type') or 'any'}"
        + (f" = {p['default']}" if p.get("default") is not None else "")
        + (f" — {p['description']}" if p.get("description") else "")
        for p in comp.get("params", [])
    )
    line = f"{comp['name']} ({comp['type']}): {comp.get('summary') or ''}"
    if params:
        line += f"\n    params: {params}"
    return line


def _candidate_signatures(reference: dict, context_info: dict,
                          stats: Optional[dict], limit: int = 8) -> List[str]:
    """Full signatures for the components most plausible at the cursor.

    The one-liner list gives the model breadth; these give it the parameter
    names/types/defaults it needs to write a correct params_hint for the
    components it is actually likely to pick.
    """
    by_name = {comp["name"]: comp for comp in reference["components"]}
    context = context_info["context"]

    if context == "brackets":
        comp = by_name.get(context_info.get("enclosing") or "")
        return [_signature_line(comp)] if comp else []

    valid_types = _valid_types_for(context)
    ranked: List[str] = []
    if context in ("pipe_stage", "after_stage") and stats:
        prev = context_info.get("prev")
        followers = (stats.get("bigrams") or {}).get(prev, {})
        ranked = [name for name, _ in
                  sorted(followers.items(), key=lambda kv: -kv[1])]
    if len(ranked) < limit and stats:
        ranked += [name for name, _ in
                   sorted((stats.get("starts") or {}).items(),
                          key=lambda kv: -kv[1])
                   if name not in ranked]

    lines = []
    for name in ranked:
        comp = by_name.get(name)
        if not comp or comp.get("error"):
            continue
        comp_type = "source" if comp["type"] == "source" else "segment"
        if comp_type not in valid_types:
            continue
        lines.append(_signature_line(comp))
        if len(lines) >= limit:
            break
    return lines


def build_prompt(script: str, cursor_offset: int, reference: dict,
                 saved: List[dict], max_suggestions: int,
                 stats: Optional[dict] = None,
                 context_info: Optional[dict] = None) -> str:
    cursor_offset = max(0, min(cursor_offset, len(script)))
    marked = script[:cursor_offset] + "<CURSOR>" + script[cursor_offset:]
    context_info = context_info or classify_cursor(script, cursor_offset)

    parts = [
        "You suggest the next component in a ChatterLang pipeline. "
        "The user is editing the script below; <CURSOR> marks their cursor.",
        SYNTAX_CRIB,
        "Available components:",
        _component_lines(reference),
    ]

    signatures = _candidate_signatures(reference, context_info, stats)
    if signatures:
        parts.append("Most likely candidates at this position, with their full "
                     "parameter signatures (prefer these, and use only their "
                     "documented parameter names):\n" + "\n".join(signatures))

    user_matches, builtin_fill = _similar_pipelines(script, saved)
    if user_matches:
        parts.append("Pipelines this user previously saved (for style and habits):")
        for record in user_matches:
            parts.append(
                f"### {record.get('name', '')}: {record.get('description', '')}\n"
                f"{record.get('script', '')}"
            )
    if builtin_fill:
        parts.append("Built-in example pipelines (for reference):")
        for record in builtin_fill:
            parts.append(
                f"### {record.get('name', '')}: {record.get('description', '')}\n"
                f"{record.get('script', '')}"
            )

    parts.append("Current script:\n" + marked)
    parts.append("Cursor context: " + _CONTEXT_INSTRUCTIONS[
        context_info["context"]].format(
            enclosing=context_info.get("enclosing") or "the component"))
    parts.append(
        f"Respond with ONLY a JSON array of at most {max_suggestions} objects, "
        'each {"segment": "<component name from the list above>", '
        '"params_hint": "<example params or empty string>", '
        '"rationale": "<one short sentence>"}. '
        "In params_hint, string values must be double-quoted "
        '(e.g. field="text") and only documented parameter names may be used. '
        "No other text."
    )
    return "\n\n".join(parts)


def parse_suggestions(raw: str, max_suggestions: int,
                      context_info: Optional[dict] = None) -> List[dict]:
    """Extract and validate the JSON array from the model output.

    Suggestions are dropped when the name isn't registered (hallucination)
    or isn't grammatically valid at the cursor (e.g. a source mid-pipeline).
    Each surviving suggestion is annotated with its component ``type`` and
    the exact ``insert`` text for the cursor position.
    """
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON array in model output")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("model output is not a JSON array")

    context_info = context_info or {"context": "statement_start",
                                    "enclosing": None, "prev": None}
    valid_types = _valid_types_for(context_info["context"])
    enclosing = context_info.get("enclosing")

    suggestions = []
    for entry in parsed[:max_suggestions * 3]:
        if not isinstance(entry, dict):
            continue
        segment = str(entry.get("segment", "")).strip()
        comp_type = _component_type_of(segment)
        if comp_type is None:
            logger.info(f"Dropping hallucinated suggestion: {segment!r}")
            continue
        if context_info["context"] == "brackets":
            if segment != enclosing:
                logger.info(f"Dropping out-of-brackets suggestion: {segment!r}")
                continue
        elif comp_type not in valid_types:
            logger.info(
                f"Dropping {comp_type} {segment!r}: invalid in "
                f"{context_info['context']} context")
            continue
        params_hint = str(entry.get("params_hint", "") or "")
        suggestions.append({
            "segment": segment,
            "type": comp_type,
            "params_hint": params_hint,
            "rationale": str(entry.get("rationale", "") or ""),
            "insert": insert_text_for(context_info, segment, params_hint, comp_type),
        })
        if len(suggestions) >= max_suggestions:
            break
    return suggestions


def suggest(script: str, cursor_offset: int, reference: dict,
            saved: List[dict], settings: Optional[dict] = None,
            max_suggestions: int = 4, stats: Optional[dict] = None) -> dict:
    """Produce the /api/suggest response payload."""
    resolved, reason = resolve_llm_status(settings)
    if not resolved:
        return {"available": False, "source": None, "model": None,
                "suggestions": [], "error": reason}
    source, model = resolved
    if not check_availability(source, model):
        return {"available": False, "source": source, "model": model,
                "suggestions": [], "error": unreachable_reason(source, model)}

    context_info = classify_cursor(script, cursor_offset)
    prompt = build_prompt(script, cursor_offset, reference, saved,
                          max_suggestions, stats=stats, context_info=context_info)
    try:
        adapter = getPromptAdapter(source)(model=model)
        # Generous cap: on "thinking" models (e.g. gemma4) the budget covers
        # reasoning tokens too — 600 leaves no room for the actual answer.
        raw = adapter.complete_text_without_context(
            prompt, temperature=0.2, max_tokens=2500
        )
    except Exception as e:
        logger.error(f"Suggestion LLM call failed: {e}")
        return {"available": True, "source": source, "model": model,
                "suggestions": [], "error": str(e)}
    try:
        suggestions = parse_suggestions(raw, max_suggestions, context_info)
    except (ValueError, json.JSONDecodeError) as e:
        logger.info(f"Unparseable suggestion output: {e}")
        return {"available": True, "source": source, "model": model,
                "suggestions": [], "error": "unparseable model output"}
    return {"available": True, "source": source, "model": model,
            "suggestions": suggestions, "error": None}
