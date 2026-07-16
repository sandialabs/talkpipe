"""Tests for the workbench pipeline workspace (store + /api/pipelines)."""

import pytest
from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench
from talkpipe.app.workbench import workspace
from talkpipe.app.workbench.workspace import WorkspaceError, WorkspaceStore, slugify, split_header


@pytest.fixture
def store(tmp_path):
    return WorkspaceStore(tmp_path)


@pytest.fixture
def client(tmp_path):
    workspace.set_workspace_dir(tmp_path)
    yield TestClient(chatterlang_workbench.app)
    workspace.set_workspace_dir(None)


SCRIPT = 'INPUT FROM echo[data="hi"] | print'


# --- WorkspaceStore unit tests ------------------------------------------------

def test_slugify():
    assert slugify("Daily RSS Summarizer!") == "daily-rss-summarizer"
    assert slugify("---") == "pipeline"
    assert slugify("a_b-c 9") == "a_b-c-9"


def test_create_and_load_roundtrip(store):
    record = store.create("My Pipeline", "does things", SCRIPT)
    assert record["id"] == "my-pipeline"
    assert record["name"] == "My Pipeline"
    assert record["created"]

    loaded = store.load("my-pipeline")
    assert loaded["script"] == SCRIPT
    assert loaded["description"] == "does things"


def test_saved_file_is_runnable_script(store, tmp_path):
    store.create("My Pipeline", "d", SCRIPT)
    content = (tmp_path / "my-pipeline.script").read_text()
    assert content.startswith("#% name: My Pipeline\n")
    # Header uses ChatterLang comments, so the file still compiles as-is.
    from talkpipe.chatterlang.compiler import compile as chatterlang_compile
    assert chatterlang_compile(content) is not None


def test_header_not_duplicated_on_resave(store):
    store.create("P", "", SCRIPT)
    loaded = store.load("p")
    store.update("p", script=loaded["script"])
    reloaded = store.load("p")
    assert reloaded["script"] == SCRIPT
    assert "#%" not in reloaded["script"]


def test_create_collision_and_overwrite(store):
    store.create("P", "", SCRIPT)
    with pytest.raises(WorkspaceError) as excinfo:
        store.create("P", "", "other")
    assert excinfo.value.status == 409
    record = store.create("P", "new desc", "NEW FROM echo | print", overwrite=True)
    assert record["description"] == "new desc"


def test_traversal_rejected(store):
    for bad_id in ["../etc/passwd", "..", "a/b", ".hidden", "UPPER"]:
        with pytest.raises(WorkspaceError):
            store.load(bad_id)


def test_rename(store, tmp_path):
    store.create("Old Name", "d", SCRIPT)
    record = store.rename("old-name", "New Name")
    assert record["id"] == "new-name"
    assert record["name"] == "New Name"
    assert not (tmp_path / "old-name.script").exists()
    assert store.load("new-name")["script"] == SCRIPT


def test_rename_collision(store):
    store.create("A", "", SCRIPT)
    store.create("B", "", SCRIPT)
    with pytest.raises(WorkspaceError) as excinfo:
        store.rename("a", "B")
    assert excinfo.value.status == 409


def test_delete(store):
    store.create("P", "", SCRIPT)
    store.delete("p")
    assert store.list() == []
    with pytest.raises(WorkspaceError) as excinfo:
        store.delete("p")
    assert excinfo.value.status == 404


def test_list_empty_when_dir_missing(tmp_path):
    store = WorkspaceStore(tmp_path / "does-not-exist")
    assert store.list() == []
    assert store.scripts() == []


def test_split_header_tolerates_manual_files():
    meta, body = split_header("INPUT FROM echo | print")
    assert meta == {}
    assert body == "INPUT FROM echo | print"


# --- API endpoint tests ---------------------------------------------------------

def test_api_crud_flow(client):
    # create
    response = client.post("/api/pipelines", json={
        "name": "Test Pipe", "description": "d", "script": SCRIPT,
    })
    assert response.status_code == 201
    pipeline_id = response.json()["id"]

    # list
    listed = client.get("/api/pipelines").json()["pipelines"]
    assert [p["id"] for p in listed] == [pipeline_id]
    assert "script" not in listed[0]

    # load
    loaded = client.get(f"/api/pipelines/{pipeline_id}").json()
    assert loaded["script"] == SCRIPT

    # update
    response = client.put(f"/api/pipelines/{pipeline_id}", json={"script": "| print"})
    assert response.status_code == 200
    assert client.get(f"/api/pipelines/{pipeline_id}").json()["script"] == "| print"

    # rename
    response = client.post(f"/api/pipelines/{pipeline_id}/rename",
                           json={"new_name": "Renamed"})
    assert response.status_code == 200
    new_id = response.json()["id"]
    assert new_id == "renamed"

    # delete
    assert client.delete(f"/api/pipelines/{new_id}").status_code == 204
    assert client.get("/api/pipelines").json()["pipelines"] == []


def test_api_create_collision_409(client):
    client.post("/api/pipelines", json={"name": "P", "script": SCRIPT})
    response = client.post("/api/pipelines", json={"name": "P", "script": SCRIPT})
    assert response.status_code == 409
    response = client.post("/api/pipelines",
                           json={"name": "P", "script": SCRIPT, "overwrite": True})
    assert response.status_code == 201


def test_api_missing_pipeline_404(client):
    assert client.get("/api/pipelines/nope").status_code == 404
    assert client.delete("/api/pipelines/nope").status_code == 404
