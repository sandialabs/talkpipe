"""Component reference (JSON) and lint endpoints for the workbench.

``GET /api/reference`` serializes the full segment/source registry (via the
same ``analyze_registered_items()`` introspection the /docs endpoints use)
for editor autocomplete and hover help. The result is cached: building it
imports every registered component, which can take seconds on first call.

``POST /api/lint`` returns structured diagnostics. ``mode="parse"`` is safe
to run on every idle keystroke: it parses and checks names against the
registries without instantiating anything. ``mode="full"`` runs the real
compiler, which instantiates component constructors (these may open files,
network connections, etc.) — it is only triggered by an explicit user action.
"""

import inspect
import logging
import re
import threading
from typing import List, Optional

from fastapi import APIRouter
from parsy import ParseError
from pydantic import BaseModel

from talkpipe.chatterlang import registry
from talkpipe.chatterlang.compiler import (
    CompileError,
    parse_error_location,
    remove_comments,
)
from talkpipe.chatterlang import compiler as chatterlang_compiler
from talkpipe.chatterlang.parsers import (
    ForkNode,
    ParsedLoop,
    ParsedPipeline,
    SegmentNode,
    script_parser,
)
from talkpipe.app import chatterlang_reference_generator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Reference cache

_reference_cache = None
_reference_lock = threading.Lock()


def _first_line(docstring: Optional[str]) -> str:
    if not docstring:
        return ""
    for line in docstring.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _component_type(item) -> str:
    if item.is_field_segment:
        return "field_segment"
    if item.is_source:
        return "source"
    return "segment"


def _build_reference() -> dict:
    items = chatterlang_reference_generator.analyze_registered_items()
    components = []
    seen_names = set()
    for item in items:
        names = [n.strip() for n in (item.chatterlang_name or item.name).split(",")]
        for name in names:
            seen_names.add(name)
            components.append({
                "name": name,
                "aliases": [n for n in names if n != name],
                "type": _component_type(item),
                "class_name": item.name,
                "summary": _first_line(item.docstring),
                "docstring": item.docstring or "",
                "params": [
                    {
                        "name": p.name,
                        "type": p.annotation or None,
                        "default": p.default or None,
                        "description": p.description or None,
                    }
                    for p in item.parameters
                ],
            })

    # Components declared by plugins that failed to import: surface them as
    # disabled entries so the editor can explain rather than just not know.
    for reg, comp_type in ((registry.input_registry, "source"),
                           (registry.segment_registry, "segment")):
        for name in reg.available_names:
            if name in seen_names:
                continue
            error = reg.load_error(name)
            if error:
                components.append({
                    "name": name,
                    "aliases": [],
                    "type": comp_type,
                    "class_name": None,
                    "summary": "",
                    "docstring": "",
                    "params": [],
                    "error": error,
                })

    components.sort(key=lambda c: c["name"].lower())
    return {"components": components}


def get_reference() -> dict:
    """The cached reference document, building it on first use."""
    global _reference_cache
    if _reference_cache is None:
        with _reference_lock:
            if _reference_cache is None:
                _reference_cache = _build_reference()
    return _reference_cache


def invalidate_reference_cache():
    global _reference_cache
    _reference_cache = None


def warm_reference_cache_async():
    """Build the reference cache in a background thread (server startup)."""
    def _warm():
        try:
            get_reference()
            logger.info("Workbench reference cache warmed")
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Failed to warm workbench reference cache: {e}")
    threading.Thread(target=_warm, daemon=True, name="workbench-reference-warm").start()


@router.get("/reference")
def api_reference():
    return get_reference()


# ---------------------------------------------------------------------------
# Lint

class LintRequest(BaseModel):
    script: str
    mode: str = "parse"


def _param_names(params) -> List[str]:
    # Param dict keys may be plain strings or Identifier nodes.
    return [k.name if hasattr(k, "name") else str(k) for k in params]


def _iter_component_uses(parsed):
    """Yield (kind, name, param_names) for every component in the AST."""
    def walk_pipeline(pipeline):
        if isinstance(pipeline, ParsedLoop):
            for inner in pipeline.pipelines:
                yield from walk_pipeline(inner)
            return
        if not isinstance(pipeline, ParsedPipeline):
            return
        node = pipeline.input_node
        if node is not None and not isinstance(node.source, str) and not node.is_variable:
            yield "source", node.source.name, _param_names(node.params)
        for transform in pipeline.transforms:
            if isinstance(transform, SegmentNode):
                yield "segment", transform.operation.name, _param_names(transform.params)
            elif isinstance(transform, ForkNode):
                for branch in transform.branches:
                    if isinstance(branch, (ParsedPipeline, ParsedLoop)):
                        yield from walk_pipeline(branch)
                    else:
                        for seg in branch:
                            if isinstance(seg, SegmentNode):
                                yield "segment", seg.operation.name, _param_names(seg.params)

    for pipeline in parsed.pipelines:
        yield from walk_pipeline(pipeline)


def _locate(script: str, name: str, used_offsets: set):
    """Best-effort (line, column) of an identifier in the source text.

    The parser AST carries no positions, so occurrences are found by text
    search; ``used_offsets`` distributes repeated names across occurrences.
    """
    for match in re.finditer(rf"\b{re.escape(name)}\b", script):
        if match.start() in used_offsets:
            continue
        used_offsets.add(match.start())
        before = script[:match.start()]
        line = before.count("\n") + 1
        column = match.start() - (before.rfind("\n") + 1) + 1
        return line, column
    return 1, 1


def _parse_mode_diagnostics(script: str) -> List[dict]:
    preprocessed = remove_comments(script)
    try:
        parsed = script_parser.parse(preprocessed)
    except ParseError as e:
        line, column = parse_error_location(preprocessed, e)
        message = chatterlang_compiler._format_parse_error(preprocessed, e)
        return [{
            "line": line or 1,
            "column": column or 1,
            "severity": "error",
            "message": message,
            "kind": "syntax",
        }]

    diagnostics = []
    used_offsets = set()
    registries = {"source": registry.input_registry, "segment": registry.segment_registry}
    for kind, name, param_names in _iter_component_uses(parsed):
        reg = registries[kind]
        if name not in reg.available_names:
            line, column = _locate(script, name, used_offsets)
            message = chatterlang_compiler._not_found_message(kind.capitalize(), name, reg)
            diagnostics.append({
                "line": line,
                "column": column,
                "severity": "error",
                "message": message,
                "kind": "unknown_name",
            })
            continue

        # Param-name check: imports the class (no instantiation). Skip when
        # the signature can't be introspected or forwards **kwargs.
        try:
            cls = reg.get(name)
            valid = chatterlang_compiler._valid_param_names(cls)
            accepts_kwargs = any(
                p.kind == p.VAR_KEYWORD
                for p in inspect.signature(cls).parameters.values()
            )
        except Exception:
            continue
        if not valid or accepts_kwargs:
            continue
        # Field segments accept field/set_as/append_as via their wrapper.
        allowed = set(valid) | {"field", "set_as", "append_as"}
        for param in param_names:
            if param not in allowed:
                line, column = _locate(script, param, used_offsets)
                diagnostics.append({
                    "line": line,
                    "column": column,
                    "severity": "warning",
                    "message": f"'{param}' is not a parameter of {kind} '{name}'. "
                               f"Valid parameters: {', '.join(valid)}.",
                    "kind": "bad_param",
                })
    return diagnostics


def _full_mode_diagnostics(script: str) -> List[dict]:
    try:
        chatterlang_compiler.compile(script)
    except CompileError as e:
        used = set()
        line, column = e.line, e.column
        if line is None and e.bad_name:
            line, column = _locate(script, e.bad_name, used)
        return [{
            "line": line or 1,
            "column": column or 1,
            "severity": "error",
            "message": str(e),
            "kind": e.kind or "compile",
        }]
    except Exception as e:
        return [{
            "line": 1,
            "column": 1,
            "severity": "error",
            "message": f"Compilation failed: {e}",
            "kind": "compile",
        }]
    return []


@router.post("/lint")
def api_lint(request: LintRequest):
    if not request.script.strip():
        return {"diagnostics": []}
    if request.mode == "full":
        return {"diagnostics": _full_mode_diagnostics(request.script)}
    return {"diagnostics": _parse_mode_diagnostics(request.script)}
