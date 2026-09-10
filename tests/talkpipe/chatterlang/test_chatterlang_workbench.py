import contextlib
import json
import logging
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app and the global store from your module.
# Adjust the import path to match your project structure.
from talkpipe.app import chatterlang_workbench


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
        # For non-interactive scripts, return some fixed output.
        return iter(["Output line 1", "Output line 2"])

    return compiled_instance


# Use an autouse fixture to monkeypatch the compile function and clear the global store.
@pytest.fixture(autouse=True)
def patch_compile(monkeypatch):
    # Override both the local reference in the endpoint module and the original import.
    monkeypatch.setattr(chatterlang_workbench, "compile", dummy_compile)
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", dummy_compile)
    # Clear the global compiled_scripts dict between tests.
    chatterlang_workbench.compiled_scripts.clear()


@pytest.fixture
def client():
    return TestClient(chatterlang_workbench.app)


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

    monkeypatch.setattr(chatterlang_workbench, "compile", dummy_compile_error)
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


def test_interactive_go_streams_error_instead_of_aborting(client, monkeypatch):
    # A pipeline that fails lazily (e.g. an unreachable LLM model) raises while
    # the response is already streaming, so we cannot switch to an error status.
    # An error line must be written into the stream body rather than dropped
    # (which the browser would render as a meaningless "network error") — but
    # only the exception class name, never the exception text, which can carry
    # paths and URLs (information exposure through an exception).
    def failing_compile(script):
        def compiled_instance(inputs):
            def gen():
                raise ValueError(
                    "refused by http://internal-host:11434 (/home/user/.secrets)"
                )
                yield  # pragma: no cover - makes this function a generator

            return gen()

        return compiled_instance

    monkeypatch.setattr(chatterlang_workbench, "compile", failing_compile)
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", failing_compile)

    compile_response = client.post("/compile", json={"script": "|chat"})
    assert compile_response.status_code == 200
    script_id = compile_response.json()["id"]

    go_response = client.post("/go", json={"id": script_id, "user_input": "hi"})
    assert go_response.status_code == 200
    output = "".join(list(go_response.iter_text()))
    assert "Error" in output
    assert "ValueError" in output
    assert "server log" in output
    assert "internal-host" not in output
    assert ".secrets" not in output


def test_interactive_go_not_found(client):
    # Call /go with a non-existent script id.
    response = client.post("/go", json={"id": str(uuid.uuid4()), "user_input": "hello"})
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Script instance not found"


def test_static_logo_served(client):
    """The workbench should serve a logo image that examples can fetch from itself."""
    response = client.get("/static/talkpipe_logo.png")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    assert len(response.content) > 0


def test_examples_include_image_example(client):
    """The /examples endpoint should expose an image example that references the workbench logo."""
    response = client.get("/examples")
    assert response.status_code == 200
    data = response.json()
    examples = data["examples"]
    assert "Image Examples" in examples
    image_examples = examples["Image Examples"]
    assert len(image_examples) >= 1
    code_blobs = "\n".join(ex["code"] for ex in image_examples)
    assert "llmVisionPrompt" in code_blobs
    assert "$workbench_logo_url" in code_blobs


def test_main_sets_workbench_logo_url(monkeypatch):
    """main() should publish a workbench_logo_url config value derived from --host / --port."""
    monkeypatch.setattr(
        "sys.argv", ["chatterlang_workbench", "--host", "127.0.0.1", "--port", "9999"]
    )
    monkeypatch.setattr(chatterlang_workbench.uvicorn, "run", lambda *a, **k: None)
    chatterlang_workbench.main()
    from talkpipe.util.config import get_config

    assert (
        get_config()["workbench_logo_url"]
        == "http://127.0.0.1:9999/static/talkpipe_logo.png"
    )


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


def test_log_queue_drops_oldest_when_full(monkeypatch):
    bounded: queue.Queue = queue.Queue(maxsize=3)
    monkeypatch.setattr(chatterlang_workbench, "log_queue", bounded)
    handler = chatterlang_workbench.QueueHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    for i in range(5):
        handler.emit(
            logging.LogRecord("t", logging.INFO, __file__, 1, f"m{i}", None, None)
        )
    assert list(bounded.queue) == ["m2", "m3", "m4"]


def test_compiled_scripts_store_evicts_least_recently_used():
    store = chatterlang_workbench._CompiledScriptStore(maxsize=2)
    store["a"] = {"instance": 1}
    store["b"] = {"instance": 2}
    assert store.get("a") is not None  # touch a → b is now the LRU
    store["c"] = {"instance": 3}
    assert "b" not in store
    assert set(store) == {"a", "c"}


def test_importing_workbench_does_not_touch_root_logger():
    # A fresh interpreter, because other tests in this module call main().
    code = (
        "import logging; from talkpipe.app import chatterlang_workbench as w; "
        "root = logging.getLogger(); "
        "assert w.queue_handler not in root.handlers, 'handler added at import'; "
        "assert root.level == logging.WARNING, root.level"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_configure_logging_is_idempotent():
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        chatterlang_workbench.configure_logging()
        chatterlang_workbench.configure_logging()
        assert root.handlers.count(chatterlang_workbench.queue_handler) == 1
    finally:
        root.handlers[:] = before


# --- Shutdown -----------------------------------------------------------------
#
# Ctrl-C used to wait for whatever request was running (a script, or the
# suggestions sidebar's LLM call) to finish before the workbench exited.


def test_main_bounds_uvicorn_graceful_shutdown(monkeypatch):
    monkeypatch.setattr("sys.argv", ["chatterlang_workbench"])
    calls = []
    monkeypatch.setattr(
        chatterlang_workbench.uvicorn, "run", lambda *a, **k: calls.append(k)
    )
    chatterlang_workbench.main()
    assert (
        calls[0]["timeout_graceful_shutdown"]
        == chatterlang_workbench.SHUTDOWN_GRACE_SECONDS
    )


def test_lingering_request_threads_ignores_daemon_and_main_threads():
    stop = threading.Event()
    worker = threading.Thread(target=stop.wait, daemon=False)
    helper = threading.Thread(target=stop.wait, daemon=True)
    worker.start()
    helper.start()
    try:
        lingering = chatterlang_workbench._lingering_request_threads()
        assert worker in lingering
        assert helper not in lingering
        assert threading.main_thread() not in lingering
    finally:
        stop.set()
        worker.join()
        helper.join()


def test_exit_without_waiting_is_a_noop_when_idle(monkeypatch):
    monkeypatch.setattr(chatterlang_workbench, "_lingering_request_threads", list)
    hard_exit = Mock()
    monkeypatch.setattr(chatterlang_workbench.os, "_exit", hard_exit)
    chatterlang_workbench._exit_without_waiting_for_requests()
    hard_exit.assert_not_called()


def test_exit_without_waiting_runs_exit_handlers_then_exits(monkeypatch, capsys):
    monkeypatch.setattr(
        chatterlang_workbench, "_lingering_request_threads", lambda: [Mock()]
    )
    order = []
    monkeypatch.setattr(
        chatterlang_workbench.atexit, "_run_exitfuncs", lambda: order.append("atexit")
    )
    monkeypatch.setattr(
        chatterlang_workbench.os, "_exit", lambda code: order.append(("exit", code))
    )
    chatterlang_workbench._exit_without_waiting_for_requests()
    assert order == ["atexit", ("exit", 0)]
    assert "without waiting for 1 running request" in capsys.readouterr().err


def test_cancelled_request_filter_drops_only_cancellations():
    import asyncio

    filt = chatterlang_workbench._cancelled_request_filter

    def record(exc):
        try:
            raise exc
        except BaseException:
            return logging.LogRecord(
                "uvicorn.error", logging.ERROR, __file__, 0, "boom", (), sys.exc_info()
            )

    assert not filt.filter(record(asyncio.CancelledError("timeout exceeded")))
    assert filt.filter(record(RuntimeError("real problem")))
    assert filt.filter(
        logging.LogRecord("x", logging.ERROR, __file__, 0, "m", (), None)
    )


def _start_workbench(workspace):
    """Start a real workbench on an ephemeral port; return (proc, port, stderr_lines)."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from talkpipe.app.chatterlang_workbench import main; main()",
            "--port",
            "0",
            "--no-llm-suggestions",
            "--workspace",
            str(workspace),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: list[str] = []
    port_found: queue.Queue[int | None] = queue.Queue()
    pattern = re.compile(r"Uvicorn running on http://127\.0\.0\.1:(\d+)")

    def drain():
        assert proc.stderr is not None
        for line in proc.stderr:
            lines.append(line)
            match = pattern.search(line)
            if match:
                port_found.put(int(match.group(1)))
        port_found.put(None)

    threading.Thread(target=drain, daemon=True).start()
    try:
        port = port_found.get(timeout=90)
    except queue.Empty:
        port = None
    if port is None:
        proc.kill()
        proc.wait()
        pytest.fail("workbench did not start:\n" + "".join(lines))
    return proc, port, lines


def _post_compile_in_background(port, script):
    body = json.dumps({"script": script}).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/compile",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    def send():
        with contextlib.suppress(Exception):
            urllib.request.urlopen(request, timeout=120)

    threading.Thread(target=send, daemon=True).start()


def _wait_for_log_line(port, needle, deadline=30):
    """Poll GET /logs until a line containing ``needle`` has been emitted."""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/logs", timeout=10
        ) as response:
            logs = json.load(response)["logs"]
        if any(needle in line for line in logs):
            return
        time.sleep(0.2)
    pytest.fail(f"never saw {needle!r} in the workbench log")


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT semantics differ")
def test_ctrl_c_exits_promptly_while_a_script_is_running(tmp_path):
    """Regression: Ctrl-C waited for the running script (here 60 s) to finish."""
    proc, port, stderr_lines = _start_workbench(tmp_path)
    try:
        _post_compile_in_background(
            port, 'INPUT FROM echo[data="1"] | sleep[seconds=60] | print'
        )
        _wait_for_log_line(port, "Executing non-interactive script")

        started = time.monotonic()
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=30)
        elapsed = time.monotonic() - started
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    stderr = "".join(stderr_lines)
    assert proc.returncode == 0, stderr
    assert elapsed < 20, f"took {elapsed:.1f}s to exit:\n{stderr}"
    assert "Exiting without waiting for 1 running request" in stderr
    assert "Exception in ASGI application" not in stderr
