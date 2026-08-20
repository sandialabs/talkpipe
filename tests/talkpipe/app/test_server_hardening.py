"""Security hardening of chatterlang_serve and chatterlang_workbench."""

import logging
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from talkpipe.app import chatterlang_workbench
from talkpipe.app.chatterlang_serve import ChatterlangServer
from talkpipe.util.config import redact


class TestServeApiKey:
    def test_default_api_key_is_none(self):
        assert ChatterlangServer().api_key is None

    def test_require_auth_without_key_generates_one(self, caplog):
        with caplog.at_level(logging.WARNING):
            server = ChatterlangServer(require_auth=True)
        assert server.api_key
        assert len(server.api_key) >= 32
        # The event is logged, but never the key itself (clear-text logging
        # of a credential); it is read from the api_key attribute instead.
        assert "generated" in caplog.text
        assert server.api_key not in caplog.text

    def test_cli_require_auth_without_key_refuses_to_start(
        self, monkeypatch, capsys, tmp_path
    ):
        # The CLI has no way to hand the operator a generated key (it is
        # never logged or printed), so starting with --require-auth and no
        # key would be a lockout; it must fail fast with guidance instead.
        import sys as _sys

        from talkpipe.app import chatterlang_serve
        from talkpipe.util.config import reset_config

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("TALKPIPE_API_KEY", raising=False)
        reset_config()
        monkeypatch.setattr(_sys, "argv", ["chatterlang_serve", "--require-auth"])
        with pytest.raises(SystemExit) as excinfo:
            chatterlang_serve.go()
        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "--api-key" in err
        assert "TALKPIPE_API_KEY" in err
        reset_config()

    def test_explicit_key_is_kept(self):
        server = ChatterlangServer(require_auth=True, api_key="abc")
        assert server.api_key == "abc"

    def test_wrong_and_missing_key_rejected(self):
        server = ChatterlangServer(require_auth=True, api_key="test-secret")
        client = TestClient(server.app)
        assert client.post("/process", json={"p": 1}).status_code == 403
        assert (
            client.post(
                "/process", json={"p": 1}, headers={"X-API-Key": "nope"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/process", json={"p": 1}, headers={"X-API-Key": "test-secret"}
            ).status_code
            == 200
        )


class TestServeSessions:
    def test_unknown_client_session_id_is_not_adopted(self):
        server = ChatterlangServer()
        attacker_id = "attacker-chosen-id"
        request = Mock()
        request.cookies.get.return_value = attacker_id
        response = Mock()

        session = server.get_or_create_session(request, response)

        assert session.session_id != attacker_id
        assert attacker_id not in server.sessions
        uuid.UUID(session.session_id)  # a fresh, well-formed id
        response.set_cookie.assert_called_once()

    def test_cookie_secure_flag_is_configurable(self):
        for flag in (False, True):
            server = ChatterlangServer(secure_cookies=flag)
            request = Mock()
            request.cookies.get.return_value = None
            response = Mock()
            server.get_or_create_session(request, response)
            assert response.set_cookie.call_args.kwargs["secure"] is flag


class TestServeFormEscaping:
    def test_form_field_values_are_html_escaped(self):
        server = ChatterlangServer(
            form_config={
                "fields": [
                    {
                        "name": "q",
                        "label": '<script>alert("x")</script>',
                        "placeholder": '"><img src=x onerror=1>',
                        "default": "a<b",
                    },
                    {
                        "name": "s",
                        "type": "select",
                        "options": ['<option>"bad'],
                    },
                    {"name": "t", "type": "textarea", "default": "</textarea><b>"},
                ]
            }
        )
        html = server._generate_form_fields()
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "onerror" not in html.replace(
            "&quot;&gt;&lt;img src=x onerror=1&gt;", ""
        )
        assert "&lt;option&gt;&quot;bad" in html
        assert "</textarea><b>" not in html
        assert "&lt;/textarea&gt;&lt;b&gt;" in html


class TestWorkbenchHostGuard:
    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5"])
    def test_loopback_hosts(self, host):
        assert chatterlang_workbench.is_loopback_host(host)

    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "example.com"])
    def test_non_loopback_hosts(self, host):
        assert not chatterlang_workbench.is_loopback_host(host)

    def test_main_refuses_remote_bind_without_flag(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["chatterlang_workbench", "--host", "0.0.0.0"])
        run = Mock()
        monkeypatch.setattr(chatterlang_workbench.uvicorn, "run", run)
        with pytest.raises(SystemExit) as exc:
            chatterlang_workbench.main()
        assert exc.value.code != 0
        assert "--allow-remote" in capsys.readouterr().err
        run.assert_not_called()

    def test_main_allows_remote_bind_with_flag(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "sys.argv",
            ["chatterlang_workbench", "--host", "0.0.0.0", "--allow-remote"],
        )
        run = Mock()
        monkeypatch.setattr(chatterlang_workbench.uvicorn, "run", run)
        chatterlang_workbench.main()
        run.assert_called_once()
        assert run.call_args.kwargs["host"] == "0.0.0.0"
        err = capsys.readouterr().err
        assert "arbitrary" in err.lower()

    def test_main_prints_banner_on_loopback(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["chatterlang_workbench"])
        run = Mock()
        monkeypatch.setattr(chatterlang_workbench.uvicorn, "run", run)
        chatterlang_workbench.main()
        run.assert_called_once()
        assert "arbitrary" in capsys.readouterr().err.lower()


class TestWorkbenchApiKey:
    @pytest.fixture
    def client(self):
        return TestClient(chatterlang_workbench.app)

    def test_no_key_configured_keeps_routes_open(self, client, monkeypatch):
        monkeypatch.setattr(chatterlang_workbench, "_configured_api_key", lambda: None)
        assert client.get("/api/pipelines").status_code == 200
        assert (
            client.post(
                "/compile", json={"script": 'INPUT FROM echo[data="hi"] | print'}
            ).status_code
            == 200
        )

    def test_key_configured_requires_header(self, client, monkeypatch):
        monkeypatch.setattr(
            chatterlang_workbench, "_configured_api_key", lambda: "wb-secret"
        )
        assert client.get("/").status_code == 200  # UI shell stays open
        assert client.get("/static/workbench/app.js").status_code == 200
        assert client.get("/api/pipelines").status_code == 401
        assert client.post("/compile", json={"script": "x"}).status_code == 401
        assert client.post("/go", json={"script": "x"}).status_code == 401
        assert (
            client.get("/api/pipelines", headers={"X-API-Key": "wrong"}).status_code
            == 401
        )
        assert (
            client.get("/api/pipelines", headers={"X-API-Key": "wb-secret"}).status_code
            == 200
        )
        assert (
            client.post(
                "/compile",
                json={"script": 'INPUT FROM echo[data="hi"] | print'},
                headers={"X-API-Key": "wb-secret"},
            ).status_code
            == 200
        )

    def test_index_installs_fetch_key_shim(self, client):
        html = client.get("/").text
        assert "X-API-Key" in html
        assert "sessionStorage" in html


class TestRedact:
    def test_redacts_secret_like_keys(self):
        cfg = {
            "openai_api_key": "sk-1",
            "API_KEY": "k",
            "email_password": "pw",
            "mongo_connection_string": "mongodb://u:p@h",
            "github_token": "t",
            "client_secret": "s",
            "default_model_name": "llama",
        }
        out = redact(cfg)
        assert out["default_model_name"] == "llama"
        for k in cfg:
            if k != "default_model_name":
                assert out[k] == "***", k
        assert cfg["API_KEY"] == "k"  # input untouched

    def test_config_load_log_is_redacted(self, tmp_path, caplog, monkeypatch):
        import talkpipe.util.config as cfgmod

        p = tmp_path / "t.toml"
        p.write_text('api_key = "supersecret"\nplain = "ok"\n')
        with caplog.at_level(logging.DEBUG, logger="talkpipe.util.config"):
            cfgmod.get_config(path=str(p), reload=True)
            cfgmod.add_config_values({"other_token": "tok123"}, override=True)
        cfgmod.reset_config()
        assert "supersecret" not in caplog.text
        assert "tok123" not in caplog.text
        assert "ok" in caplog.text
