"""REST endpoints for the pipeline workspace (/api/pipelines)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from talkpipe.app.workbench.workspace import WorkspaceError, get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Callbacks fired after any mutation (e.g. corpus rebuild in suggest_api).
_change_listeners = []


def on_workspace_change(callback):
    _change_listeners.append(callback)


def _notify_change():
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
    name: Optional[str] = None
    description: Optional[str] = None
    script: Optional[str] = None


class PipelineRename(BaseModel):
    new_name: str


def _run(operation):
    try:
        return operation()
    except WorkspaceError as e:
        raise HTTPException(status_code=e.status, detail=str(e))


@router.get("/pipelines")
def list_pipelines():
    return {"pipelines": _run(lambda: get_store().list())}


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str):
    return _run(lambda: get_store().load(pipeline_id))


@router.post("/pipelines", status_code=201)
def create_pipeline(request: PipelineCreate):
    record = _run(lambda: get_store().create(
        request.name, request.description, request.script,
        overwrite=request.overwrite,
    ))
    _notify_change()
    return record


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: str, request: PipelineUpdate):
    record = _run(lambda: get_store().update(
        pipeline_id,
        name=request.name,
        description=request.description,
        script=request.script,
    ))
    _notify_change()
    return record


@router.post("/pipelines/{pipeline_id}/rename")
def rename_pipeline(pipeline_id: str, request: PipelineRename):
    record = _run(lambda: get_store().rename(pipeline_id, request.new_name))
    _notify_change()
    return record


@router.delete("/pipelines/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str):
    _run(lambda: get_store().delete(pipeline_id))
    _notify_change()
    return Response(status_code=204)
