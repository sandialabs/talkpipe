"""Suggestion and settings endpoints for the workbench.

- ``GET /api/suggest/stats``: co-occurrence tables mined from the built-in
  examples, shipped seed scripts, and the user's saved pipelines. The client
  ranks candidates locally from these tables (zero-latency); this endpoint
  only mines. Tables are cached and rebuilt after any workspace change.
- ``POST /api/suggest``: LLM suggestions (see ``suggest.py``).
- ``GET/PUT /api/settings``: suggestion model overrides + auto-suggest flag,
  persisted to ``<workspace>/settings.json``.
"""

import json
import logging
import threading
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from talkpipe.app.workbench import corpus, reference_api, suggest, workspace_api
from talkpipe.app.workbench.workspace import get_store, resolve_workspace_dir
from talkpipe.llm.config import getPromptSources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

SETTINGS_FILENAME = "settings.json"
SETTINGS_KEYS = ("suggest_source", "suggest_model", "auto_suggest")

# --- Heuristic stats cache ----------------------------------------------------

_stats_cache = None
_stats_lock = threading.Lock()


def invalidate_stats_cache():
    global _stats_cache
    _stats_cache = None


workspace_api.on_workspace_change(invalidate_stats_cache)


def get_stats() -> dict:
    global _stats_cache
    if _stats_cache is None:
        with _stats_lock:
            if _stats_cache is None:
                _stats_cache = corpus.build_corpus_tables(get_store().scripts())
    return _stats_cache


@router.get("/suggest/stats")
def api_suggest_stats():
    return get_stats()


# --- Settings -------------------------------------------------------------------

def _settings_path():
    return resolve_workspace_dir() / SETTINGS_FILENAME


def load_settings() -> dict:
    path = _settings_path()
    settings = {"suggest_source": None, "suggest_model": None, "auto_suggest": False}
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            for key in SETTINGS_KEYS:
                if key in stored:
                    settings[key] = stored[key]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Ignoring unreadable workbench settings: {e}")
    return settings


def save_settings(settings: dict):
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _resolved_status(settings: dict) -> dict:
    resolved = suggest.resolve_llm(settings)
    if not resolved:
        return {"available": False, "source": None, "model": None,
                "reason": "no model configured"}
    source, model = resolved
    available = suggest.check_availability(source, model)
    return {"available": available, "source": source, "model": model,
            "reason": None if available else "model not reachable"}


class SettingsUpdate(BaseModel):
    suggest_source: Optional[str] = None
    suggest_model: Optional[str] = None
    auto_suggest: Optional[bool] = None


def _settings_response(settings: dict) -> dict:
    return {
        **settings,
        "known_sources": getPromptSources(),
        "resolved": _resolved_status(settings),
    }


@router.get("/settings")
def api_get_settings():
    return _settings_response(load_settings())


@router.put("/settings")
def api_put_settings(request: SettingsUpdate):
    settings = load_settings()
    update = request.model_dump(exclude_unset=True)
    for key in SETTINGS_KEYS:
        if key in update:
            settings[key] = update[key]
    save_settings(settings)
    suggest.invalidate_availability_cache()
    return _settings_response(settings)


# --- LLM suggestions ----------------------------------------------------------------

class SuggestRequest(BaseModel):
    script: str
    cursor_offset: int = 0
    max_suggestions: int = 4


@router.post("/suggest")
def api_suggest(request: SuggestRequest):
    settings = load_settings()
    resolved = suggest.resolve_llm(settings)
    saved = []
    if resolved:
        # Only pay for loading saved pipelines when a model will see them.
        store = get_store()
        saved = [store.load(record["id"]) for record in store.list()]
    return suggest.suggest(
        request.script,
        request.cursor_offset,
        reference_api.get_reference(),
        saved,
        settings=settings,
        max_suggestions=max(1, min(request.max_suggestions, 10)),
    )
