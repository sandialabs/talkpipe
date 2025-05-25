import uuid
import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app and the global store from your module.
# Adjust the import path to match your project structure.
from talkpipe.app import chatterlang_server

# Define a dummy compile function to replace the real compiler.
def dummy_compile(script):
    """
    A dummy compile function that returns a callable.
    For non-interactive scripts (when called with an empty list),
    it returns a fixed iterator of output lines.
    For interactive scripts (when provided input), it returns a response
    that echoes the input.
    """
    def compiled_instance(inputs):
        if inputs:
            # For interactive scripts, return an iterator over a response line.
            return iter([f"Interactive response to: {inputs[0]}"])
        else:
            # For non-interactive scripts, return some fixed output.
            return iter(["Output line 1", "Output line 2"])
    return compiled_instance

# Use an autouse fixture to monkeypatch the compile function and clear the global store.
@pytest.fixture(autouse=True)
def patch_compile(monkeypatch):
    # Override both the local reference in the endpoint module and the original import.
    monkeypatch.setattr(chatterlang_server, "compile", dummy_compile)
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", dummy_compile)
    # Clear the global compiled_scripts dict between tests.
    chatterlang_server.compiled_scripts.clear()

@pytest.fixture
def client():
    return TestClient(chatterlang_server.app)

def test_compile_non_interactive(client):
    # A non-interactive script: first non-blank non-CONST line does not start with '|'
    script = "print('Hello World')"
    response = client.post("/compile", json={"script": script})
    assert response.status_code == 200
    data = response.json()
    # Check that an ID was returned and the script is marked as non-interactive.
    assert "id" in data
    assert data["interactive"] is False
    # The dummy compile returns two output lines.
    expected_output = "Output line 1\nOutput line 2"
    assert data["output"] == expected_output

def test_compile_interactive(client):
    # An interactive script: first non-blank non-CONST line starts with '|'
    script = "   \nCONST something\n|interactive script"
    response = client.post("/compile", json={"script": script})
    assert response.status_code == 200
    data = response.json()
    # Check that an ID was returned and the script is marked as interactive.
    assert "id" in data
    assert data["interactive"] is True
    # For interactive scripts, no immediate output is returned.
    assert "output" not in data

def test_compile_empty_script(client):
    # Test that an empty script returns a 400 error.
    response = client.post("/compile", json={"script": ""})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Script content is required"

def test_compile_error(client, monkeypatch):
    # Force the dummy compile to raise an exception to simulate a compilation error.
    def dummy_compile_error(script):
        raise Exception("dummy compilation failure")
    
    monkeypatch.setattr(chatterlang_server, "compile", dummy_compile_error)
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", dummy_compile_error)
    
    script = "some script"
    response = client.post("/compile", json={"script": script})
    assert response.status_code == 400
    data = response.json()
    assert "Compilation error:" in data["detail"]

def test_interactive_go(client):
    # First compile an interactive script.
    script = "|interactive script"
    compile_response = client.post("/compile", json={"script": script})
    assert compile_response.status_code == 200
    compile_data = compile_response.json()
    script_id = compile_data["id"]
    assert compile_data["interactive"] is True
    
    # Now call the /go endpoint with valid interactive input.
    go_response = client.post("/go", json={"id": script_id, "user_input": "hello"})
    assert go_response.status_code == 200
    # The response is a streaming response; accumulate all output.
    output = "".join(list(go_response.iter_text()))
    assert "Interactive response to: hello" in output

def test_interactive_go_not_found(client):
    # Call /go with a non-existent script id.
    response = client.post("/go", json={"id": str(uuid.uuid4()), "user_input": "hello"})
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Script instance not found"

def test_interactive_go_non_interactive(client):
    # Compile a non-interactive script and then call /go.
    script = "print('Hello World')"
    compile_response = client.post("/compile", json={"script": script})
    compile_data = compile_response.json()
    script_id = compile_data["id"]
    
    # /go should return a 400 error for a non-interactive script.
    go_response = client.post("/go", json={"id": script_id, "user_input": "hello"})
    assert go_response.status_code == 400
    data = go_response.json()
    assert data["detail"] == "This script is not interactive"
