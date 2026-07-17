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
AVAILABILITY_TTL_SECONDS = 60


def check_availability(source: str, model: str) -> bool:
    """Whether the adapter reports itself available (cached ~60s)."""
    key = (source, model)
    cached = _availability_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[1] < AVAILABILITY_TTL_SECONDS:
        return cached[0]
    try:
        adapter = getPromptAdapter(source)(model=model)
        available = bool(adapter.is_available())
    except Exception as e:
        logger.info(f"Suggestion LLM unavailable ({source}/{model}): {e}")
        available = False
    _availability_cache[key] = (available, now)
    return available


def invalidate_availability_cache():
    _availability_cache.clear()


def _registered_names() -> set:
    return set(registry.input_registry.available_names) | set(
        registry.segment_registry.available_names
    )


def _component_lines(reference: dict) -> str:
    lines = []
    for comp in reference["components"]:
        if comp.get("error"):
            continue
        summary = comp.get("summary") or ""
        lines.append(f"- {comp['name']} ({comp['type']}): {summary}"[:160])
    return "\n".join(lines)


def _similar_pipelines(script: str, saved: List[dict], limit: int = 3) -> List[dict]:
    """Saved pipelines ranked by Jaccard similarity of component-name sets."""
    from talkpipe.app.workbench.corpus import mine_script

    current = {name for chain in mine_script(script) for name in chain}
    if not current:
        return saved[:limit]
    scored = []
    for record in saved:
        other = {name for chain in mine_script(record.get("script", "")) for name in chain}
        if not other:
            continue
        score = len(current & other) / len(current | other)
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [record for _, record in scored[:limit]]


def build_prompt(script: str, cursor_offset: int, reference: dict,
                 saved: List[dict], max_suggestions: int) -> str:
    cursor_offset = max(0, min(cursor_offset, len(script)))
    marked = script[:cursor_offset] + "<CURSOR>" + script[cursor_offset:]

    parts = [
        "You suggest the next component in a ChatterLang pipeline. "
        "The user is editing the script below; <CURSOR> marks their cursor.",
        SYNTAX_CRIB,
        "Available components:",
        _component_lines(reference),
    ]
    similar = _similar_pipelines(script, saved)
    if similar:
        parts.append("Pipelines this user previously saved (for style and habits):")
        for record in similar:
            parts.append(
                f"### {record.get('name', '')}: {record.get('description', '')}\n"
                f"{record.get('script', '')}"
            )
    parts.append("Current script:\n" + marked)
    parts.append(
        f"Respond with ONLY a JSON array of at most {max_suggestions} objects, "
        'each {"segment": "<component name from the list above>", '
        '"params_hint": "<example params or empty string>", '
        '"rationale": "<one short sentence>"}. No other text.'
    )
    return "\n\n".join(parts)


def parse_suggestions(raw: str, max_suggestions: int) -> List[dict]:
    """Extract and validate the JSON array from the model output."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON array in model output")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("model output is not a JSON array")

    registered = _registered_names()
    suggestions = []
    for entry in parsed[:max_suggestions * 2]:
        if not isinstance(entry, dict):
            continue
        segment = str(entry.get("segment", "")).strip()
        if segment not in registered:
            logger.info(f"Dropping hallucinated suggestion: {segment!r}")
            continue
        suggestions.append({
            "segment": segment,
            "params_hint": str(entry.get("params_hint", "") or ""),
            "rationale": str(entry.get("rationale", "") or ""),
        })
        if len(suggestions) >= max_suggestions:
            break
    return suggestions


def suggest(script: str, cursor_offset: int, reference: dict,
            saved: List[dict], settings: Optional[dict] = None,
            max_suggestions: int = 4) -> dict:
    """Produce the /api/suggest response payload."""
    resolved = resolve_llm(settings)
    if not resolved:
        return {"available": False, "source": None, "model": None,
                "suggestions": [], "error": None}
    source, model = resolved
    if not check_availability(source, model):
        return {"available": False, "source": source, "model": model,
                "suggestions": [], "error": unreachable_reason(source, model)}

    prompt = build_prompt(script, cursor_offset, reference, saved, max_suggestions)
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
        suggestions = parse_suggestions(raw, max_suggestions)
    except (ValueError, json.JSONDecodeError) as e:
        logger.info(f"Unparseable suggestion output: {e}")
        return {"available": True, "source": source, "model": model,
                "suggestions": [], "error": "unparseable model output"}
    return {"available": True, "source": source, "model": model,
            "suggestions": suggestions, "error": None}
