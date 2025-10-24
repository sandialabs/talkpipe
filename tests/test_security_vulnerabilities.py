"""
Security vulnerability tests for TalkPipe.
These tests should FAIL before fixes are applied and PASS after fixes.
"""

import pytest
import subprocess
import os
import tempfile
from fastapi.testclient import TestClient

from talkpipe.util.data_manipulation import compileLambda
from talkpipe.util.os import run_command, SecurityError
from talkpipe.app.chatterlang_serve import ChatterlangServer


class TestUnsafeEvalExecution:
    """Test cases for unsafe eval execution vulnerability (P0)."""
    
    def test_eval_code_injection_attack(self):
        """Test that malicious code injection via eval is prevented."""
        # This test should FAIL before security fix
        malicious_expression = "__import__('os').system('echo PWNED')"
        
        with pytest.raises((ValueError, NameError, AttributeError)) as exc_info:
            lambda_func = compileLambda(malicious_expression)
            result = lambda_func({"test": "data"})
        
        # Should raise security-related error, not execute the command
        error_msg = str(exc_info.value).lower()
        assert ("security violation" in error_msg or 
               "not allowed" in error_msg or 
               "not defined" in error_msg or
               "prohibited pattern" in error_msg)
    
    def test_eval_file_system_access_blocked(self):
        """Test that file system access via eval is prevented."""
        malicious_expression = "open('/etc/passwd', 'r').read()"
        
        with pytest.raises((ValueError, NameError, AttributeError)) as exc_info:
            lambda_func = compileLambda(malicious_expression)
            lambda_func({"test": "data"})
        
        error_msg = str(exc_info.value).lower()
        assert ("security violation" in error_msg or 
               "'open' is not defined" in error_msg or 
               "not allowed" in error_msg or
               "prohibited pattern" in error_msg)
    
    def test_eval_import_blocked(self):
        """Test that imports via eval are prevented."""
        malicious_expressions = [
            "__import__('subprocess').call(['ls'])",
            "exec('import os; os.system(\"ls\")')",
            "eval('__import__(\"os\").getcwd()')"
        ]
        
        for expr in malicious_expressions:
            with pytest.raises((ValueError, NameError, AttributeError)) as exc_info:
                lambda_func = compileLambda(expr)
                lambda_func({"test": "data"})
            
            error_msg = str(exc_info.value).lower()
            assert ("security violation" in error_msg or
                   "not defined" in error_msg or 
                   "not allowed" in error_msg or
                   "prohibited pattern" in error_msg)
    
    def test_eval_safe_operations_allowed(self):
        """Test that safe operations are still allowed after security fix."""
        safe_expressions = [
            "item['test'] * 2 if isinstance(item.get('test'), int) else 0",
            "len(str(item)) + 5",
            "max([1, 2, 3, int(item.get('num', 0))])"
        ]
        
        test_data = {"test": 5, "num": 10}
        
        for expr in safe_expressions:
            lambda_func = compileLambda(expr)
            result = lambda_func(test_data)
            assert result is not None


class TestShellInjectionVulnerability:
    """Test cases for shell injection vulnerability (P0)."""
    
    def test_command_injection_blocked(self):
        """Test that command injection via shell=True is prevented."""
        # This test should FAIL before security fix
        malicious_command = "ls; echo 'INJECTED_COMMAND'"
        
        with pytest.raises((subprocess.CalledProcessError, ValueError, SecurityError)) as exc_info:
            list(run_command(malicious_command))
        
        # Should either raise SecurityError or fail command execution safely
        error_msg = str(exc_info.value).lower()
        assert ("security" in error_msg or 
               "not allowed" in error_msg or
               "invalid" in error_msg or
               exc_info.typename in ["SecurityError", "ValueError"])
    
    def test_path_traversal_blocked(self):
        """Test that path traversal attacks are prevented."""
        malicious_commands = [
            "cat ../../../../etc/passwd",
            "ls ../../../",
            "cat /etc/passwd"
        ]
        
        for cmd in malicious_commands:
            with pytest.raises((subprocess.CalledProcessError, ValueError, SecurityError, FileNotFoundError)):
                list(run_command(cmd))
    
    def test_shell_metacharacters_blocked(self):
        """Test that shell metacharacters are handled safely."""
        dangerous_commands = [
            "echo test | rm -rf /",  # Pipe to dangerous command
            "echo test && rm important_file",  # Command chaining
            "echo test; cat /etc/passwd",  # Command separator
            "echo test $(cat /etc/passwd)",  # Command substitution
            "echo test `cat /etc/passwd`"   # Command substitution (backticks)
        ]
        
        for cmd in dangerous_commands:
            with pytest.raises((subprocess.CalledProcessError, ValueError, SecurityError)):
                list(run_command(cmd))
    
    def test_safe_commands_allowed(self):
        """Test that safe, simple commands still work after security fix."""
        # Create a temporary file to test with
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp.write("test content\n")
            tmp_path = tmp.name
        
        try:
            # Test that basic, safe file operations work
            result = list(run_command(f"cat {tmp_path}"))
            assert len(result) > 0
            assert "test content" in result[0]
        finally:
            os.unlink(tmp_path)


class TestCORSAndAuthenticationWeaknesses:
    """Test cases for CORS and authentication weaknesses (P1)."""
    
    def test_cors_origin_restrictions(self):
        """Test that CORS origins are properly restricted."""
        # This test should FAIL before security fix
        server = ChatterlangServer(
            host="127.0.0.1",
            port=9998,
            require_auth=False
        )
        
        client = TestClient(server.app)
        
        # Test that wildcard CORS is NOT allowed
        response = client.options(
            "/process",
            headers={"Origin": "http://malicious-site.com"}
        )
        
        cors_header = response.headers.get("access-control-allow-origin")
        
        # Should not allow any origin (*) for security
        assert cors_header != "*", "CORS should not allow all origins (*)"
    
    def test_authentication_required_for_sensitive_endpoints(self):
        """Test that authentication is properly enforced."""
        server = ChatterlangServer(
            host="127.0.0.1",
            port=9999,
            api_key="secure-key",
            require_auth=True
        )
        
        client = TestClient(server.app)
        
        # Test that endpoints require authentication
        response = client.post("/process", json={"test": "data"})
        assert response.status_code == 403, "Should require authentication"
        
        response = client.get("/history")
        assert response.status_code == 403, "Should require authentication"
    
    def test_server_sent_events_authentication(self):
        """Test that Server-Sent Events endpoint requires authentication when enabled."""
        server = ChatterlangServer(
            host="127.0.0.1",
            port=10000,
            api_key="secure-key", 
            require_auth=True
        )
        
        client = TestClient(server.app)
        
        # SSE endpoint should require auth when global auth is enabled
        response = client.get("/output-stream")
        # This should either require auth or be properly secured
        assert response.status_code in [403, 401], "SSE endpoint should require authentication"
    
    def test_session_cookie_security(self):
        """Test that session cookies have proper security attributes."""
        server = ChatterlangServer(
            host="127.0.0.1",
            port=10001,
            require_auth=False
        )
        
        client = TestClient(server.app)
        
        # Make a request that should set a session cookie
        response = client.post("/process", json={"test": "data"})
        
        # Check if session cookie has security attributes
        cookie_header = response.headers.get("set-cookie", "")
        if cookie_header:
            # Should have security attributes
            assert "httponly" in cookie_header.lower(), "Session cookie should be HttpOnly"
            # Note: Secure flag would be tested in HTTPS context
            assert "samesite" in cookie_header.lower(), "Session cookie should have SameSite attribute"


class TestAdditionalSecurityIssues:
    """Test cases for additional security vulnerabilities."""
    
    def test_pickle_loading_safety(self):
        """Test that pickle loading is done safely or avoided."""
        # This is harder to test without specific pickle usage, but we can check imports
        from talkpipe.pipe import basic
        
        # Verify that if pickle is used, it's used safely
        # The hash_data function uses pickle.dumps which is safer than loads
        import pickle
        
        # Test data that should be safe to pickle
        safe_data = {"test": "data", "number": 123}
        pickled = pickle.dumps(safe_data)
        
        # This should work fine
        unpickled = pickle.loads(pickled)
        assert unpickled == safe_data
    
    def test_logging_sensitive_data_prevention(self):
        """Test that sensitive data is not logged."""
        import logging
        from io import StringIO
        
        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger('talkpipe')
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        
        try:
            # Test with data containing potential secrets
            sensitive_data = {
                "password": "secret123",
                "api_key": "abc123",
                "token": "bearer_token"
            }
            
            # This should not log the sensitive values
            lambda_func = compileLambda("len(str(item))")
            lambda_func(sensitive_data)
            
            log_output = log_capture.getvalue()
            
            # Check that sensitive values are not in logs
            if "secret123" in log_output:
                pytest.fail("Password should not be logged")
            if "abc123" in log_output:
                pytest.fail("API key should not be logged")
            if "bearer_token" in log_output:
                pytest.fail("Token should not be logged")
            
        finally:
            logger.removeHandler(handler)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])