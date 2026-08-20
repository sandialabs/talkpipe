"""REST endpoints for the pipeline workspace (/api/pipelines)."""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from talkpipe.app.workbench.workspace import WorkspaceError, get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Callbacks fired after any mutation (e.g. corpus rebuild in suggest_api).
_change_listeners: list[Callable[..., Any]] = []


def on_workspace_change(callback: Callable[..., Any]) -> None:
    _change_listeners.append(callback)


def _notify_change() -> None:
    for callback in _change_listeners:
        try:
            callback()
        except Exception as e:  # pragma: no cover - listeners must not break saves
            logger.warning(f"Workspace change listener failed: {e}")


class PipelineCreate(BaseModel):
    name: str
    description: str = ""
    script: str
    overwrite: bool = False


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    script: str | None = None


class PipelineRename(BaseModel):
    new_name: str


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e


@router.get("/pipelines")
def list_pipelines() -> dict[str, Any]:
    return {"pipelines": _run(lambda: get_store().list())}


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str) -> Any:
    return _run(lambda: get_store().load(pipeline_id))


@router.post("/pipelines", status_code=201)
def create_pipeline(request: PipelineCreate) -> Any:
    record = _run(
        lambda: get_store().create(
            request.name,
            request.description,
            request.script,
            overwrite=request.overwrite,
        )
    )
    _notify_change()
    return record


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: str, request: PipelineUpdate) -> Any:
    record = _run(
        lambda: get_store().update(
            pipeline_id,
            name=request.name,
            description=request.description,
            script=request.script,
        )
    )
    _notify_change()
    return record


@router.post("/pipelines/{pipeline_id}/rename")
def rename_pipeline(pipeline_id: str, request: PipelineRename) -> Any:
    record = _run(lambda: get_store().rename(pipeline_id, request.new_name))
    _notify_change()
    return record


@router.delete("/pipelines/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str) -> Response:
    _run(lambda: get_store().delete(pipeline_id))
    _notify_change()
    return Response(status_code=204)
