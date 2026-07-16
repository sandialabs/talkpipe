"""File-backed pipeline workspace for the workbench.

Pipelines are stored as plain ``.script`` files in a workspace directory so
they remain directly runnable with ``chatterlang_script`` and friendly to
manual editing / version control. Metadata lives in a ``#%`` comment header
at the top of each file (``#`` is a ChatterLang comment, so the header never
affects execution)::

    #% name: Daily article summarizer
    #% description: Downloads a URL list and summarizes each page
    #% created: 2026-07-16T12:00:00+00:00
    INPUT FROM ...

The pipeline id is the filename stem (a slug of the name at creation time);
``modified`` comes from the file's mtime and is never stored in the header.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from talkpipe.util.config import get_config

DEFAULT_WORKSPACE = "~/.talkpipe/workbench"
HEADER_PREFIX = "#%"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

_workspace_override: Optional[Path] = None


class WorkspaceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def set_workspace_dir(path):
    """Explicitly set the workspace directory (CLI/tests). None resets."""
    global _workspace_override
    _workspace_override = Path(path).expanduser() if path else None


def resolve_workspace_dir() -> Path:
    if _workspace_override is not None:
        return _workspace_override
    configured = get_config().get("workbench_workspace")
    return Path(configured or DEFAULT_WORKSPACE).expanduser()


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "pipeline"


def split_header(text: str):
    """Split file content into (metadata dict, script body)."""
    meta = {}
    lines = text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith(HEADER_PREFIX):
            key, _, value = line[len(HEADER_PREFIX):].partition(":")
            meta[key.strip()] = value.strip()
            body_start = i + 1
        else:
            break
    body = "\n".join(lines[body_start:])
    return meta, body.lstrip("\n")


def build_header(name: str, description: str, created: str) -> str:
    header = [f"{HEADER_PREFIX} name: {name}"]
    if description:
        header.append(f"{HEADER_PREFIX} description: {description}")
    header.append(f"{HEADER_PREFIX} created: {created}")
    return "\n".join(header) + "\n"


class WorkspaceStore:
    """CRUD over the ``.script`` files in one workspace directory."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser()

    def _ensure_root(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, pipeline_id: str) -> Path:
        if not ID_PATTERN.match(pipeline_id):
            raise WorkspaceError(f"Invalid pipeline id: {pipeline_id!r}")
        path = (self.root / f"{pipeline_id}.script").resolve()
        if path.parent != self.root.resolve():
            raise WorkspaceError(f"Invalid pipeline id: {pipeline_id!r}")
        return path

    def _record(self, path: Path, include_script: bool) -> dict:
        text = path.read_text(encoding="utf-8")
        meta, body = split_header(text)
        record = {
            "id": path.stem,
            "name": meta.get("name", path.stem),
            "description": meta.get("description", ""),
            "created": meta.get("created", ""),
            "modified": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }
        if include_script:
            record["script"] = body
        return record

    def list(self) -> List[dict]:
        if not self.root.is_dir():
            return []
        records = [
            self._record(path, include_script=False)
            for path in sorted(self.root.glob("*.script"))
        ]
        records.sort(key=lambda r: r["name"].lower())
        return records

    def load(self, pipeline_id: str) -> dict:
        path = self._path_for(pipeline_id)
        if not path.is_file():
            raise WorkspaceError(f"Pipeline '{pipeline_id}' not found", status=404)
        return self._record(path, include_script=True)

    def scripts(self) -> List[str]:
        """All stored script bodies (for corpus mining)."""
        if not self.root.is_dir():
            return []
        return [
            split_header(path.read_text(encoding="utf-8"))[1]
            for path in self.root.glob("*.script")
        ]

    def create(self, name: str, description: str, script: str,
               overwrite: bool = False) -> dict:
        if not name.strip():
            raise WorkspaceError("Pipeline name is required")
        self._ensure_root()
        pipeline_id = slugify(name)
        path = self._path_for(pipeline_id)
        if path.exists() and not overwrite:
            raise WorkspaceError(
                f"A pipeline with id '{pipeline_id}' already exists", status=409
            )
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._write(path, name.strip(), description.strip(), created, script)
        return self._record(path, include_script=False)

    def update(self, pipeline_id: str, name: Optional[str] = None,
               description: Optional[str] = None,
               script: Optional[str] = None) -> dict:
        path = self._path_for(pipeline_id)
        if not path.is_file():
            raise WorkspaceError(f"Pipeline '{pipeline_id}' not found", status=404)
        meta, body = split_header(path.read_text(encoding="utf-8"))
        self._write(
            path,
            (name if name is not None else meta.get("name", pipeline_id)).strip(),
            (description if description is not None else meta.get("description", "")).strip(),
            meta.get("created", ""),
            script if script is not None else body,
        )
        return self._record(path, include_script=False)

    def rename(self, pipeline_id: str, new_name: str) -> dict:
        if not new_name.strip():
            raise WorkspaceError("New name is required")
        path = self._path_for(pipeline_id)
        if not path.is_file():
            raise WorkspaceError(f"Pipeline '{pipeline_id}' not found", status=404)
        new_id = slugify(new_name)
        new_path = self._path_for(new_id)
        if new_path != path and new_path.exists():
            raise WorkspaceError(
                f"A pipeline with id '{new_id}' already exists", status=409
            )
        meta, body = split_header(path.read_text(encoding="utf-8"))
        self._write(new_path, new_name.strip(), meta.get("description", ""),
                    meta.get("created", ""), body)
        if new_path != path:
            path.unlink()
        return self._record(new_path, include_script=False)

    def delete(self, pipeline_id: str):
        path = self._path_for(pipeline_id)
        if not path.is_file():
            raise WorkspaceError(f"Pipeline '{pipeline_id}' not found", status=404)
        path.unlink()

    def _write(self, path: Path, name: str, description: str, created: str, script: str):
        # Never nest headers if the incoming script still carries one.
        _, body = split_header(script)
        content = build_header(name, description, created) + body
        if not content.endswith("\n"):
            content += "\n"
        path.write_text(content, encoding="utf-8")


def get_store() -> WorkspaceStore:
    return WorkspaceStore(resolve_workspace_dir())
