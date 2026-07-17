"""--load-module handling for the workbench.

``main()`` records the module paths in ``TALKPIPE_workbench_load_modules``
and the app imports them at startup (in ``_lifespan``), so custom components
survive uvicorn's ``--reload`` subprocess, which re-imports the app in a
fresh process where only the environment is inherited.
"""

import textwrap

from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench
from talkpipe.util.config import reset_config

MODULE_SOURCE = textwrap.dedent(
    '''
    from talkpipe.pipe import core
    from talkpipe.chatterlang import registry


    @registry.register_segment("wbTestShout")
    @core.segment()
    def wbTestShout(items):
        """Uppercase each item (test helper segment)."""
        for item in items:
            yield str(item).upper()
    '''
)


def test_configured_modules_loaded_at_app_startup(tmp_path, monkeypatch):
    module = tmp_path / "custom_segments.py"
    module.write_text(MODULE_SOURCE)
    monkeypatch.setenv("TALKPIPE_workbench_load_modules", str(module))
    reset_config()
    try:
        # Entering the client context runs the app lifespan, exactly like a
        # fresh uvicorn (reload child) process would.
        with TestClient(chatterlang_workbench.app) as client:
            response = client.post(
                "/compile",
                json={"script": 'INPUT FROM echo[data="hi"] | wbTestShout'},
            )
            assert response.status_code == 200
            assert response.json()["output"] == "HI"
    finally:
        reset_config()


def test_missing_configured_module_does_not_break_startup(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TALKPIPE_workbench_load_modules", str(tmp_path / "nope.py")
    )
    reset_config()
    try:
        with TestClient(chatterlang_workbench.app) as client:
            response = client.post(
                "/compile", json={"script": 'INPUT FROM echo[data="x"] | print'}
            )
            assert response.status_code == 200
    finally:
        reset_config()
