import pytest
import json
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from queue import Queue

from talkpipe.app.chatterlang_serve import (
    ChatterlangServer,
    UserSession,
    FormField,
    FormConfig,
    DataResponse,
    ChatterlangServerSegment,
    load_form_config,
    go
)


class TestFormField:
    """Test FormField model."""
    
    def test_default_values(self):
        """Test FormField with default values."""
        field = FormField(name="test_field")
        assert field.name == "test_field"
        assert field.type == "text"
        assert field.label is None
        assert field.required is False
        assert field.persist is False
    
    def test_custom_values(self):
        """Test FormField with custom values."""
        field = FormField(
            name="test_field",
            type="number",
            label="Test Label",
            placeholder="Enter value",
            required=True,
            default=42,
            options=["opt1", "opt2"],
            min=0,
            max=100,
            rows=5,
            persist=True
        )
        assert field.name == "test_field"
        assert field.type == "number"
        assert field.label == "Test Label"
        assert field.placeholder == "Enter value"
        assert field.required is True
        assert field.default == 42
        assert field.options == ["opt1", "opt2"]
        assert field.min == 0
        assert field.max == 100
        assert field.rows == 5
        assert field.persist is True


class TestFormConfig:
    """Test FormConfig model."""
    
    def test_default_values(self):
        """Test FormConfig with default values."""
        config = FormConfig()
        assert config.title == "Data Input Form"
        assert config.fields == []
        assert config.position == "bottom"
        assert config.height == "150px"
        assert config.theme == "dark"
    
    def test_custom_values(self):
        """Test FormConfig with custom values."""
        fields = [FormField(name="test")]
        config = FormConfig(
            title="Custom Form",
            fields=fields,
            position="top",
            height="200px",
            theme="light"
        )
        assert config.title == "Custom Form"
        assert config.fields == fields
        assert config.position == "top"
        assert config.height == "200px"
        assert config.theme == "light"


class TestUserSession:
    """Test UserSession class."""
    
    def test_init(self):
        """Test UserSession initialization."""
        session = UserSession("test-session-id")
        assert session.session_id == "test-session-id"
        assert session.history == []
        assert session.history_length == 1000
        assert session.compiled_script is None
        assert isinstance(session.last_activity, datetime)
    
    def test_init_with_script(self):
        """Test UserSession initialization with script content."""
        with patch('talkpipe.app.chatterlang_serve.compile') as mock_compile:
            mock_compiled = Mock()
            mock_compiled.as_function.return_value = mock_compiled
            mock_compile.return_value = mock_compiled
            
            session = UserSession("test-session-id", "| print")

            mock_compile.assert_called_once_with("| print")
            assert session.compiled_script == mock_compiled
    
    def test_compile_script_success(self):
        """Test successful script compilation."""
        session = UserSession("test-session-id")
        
        with patch('talkpipe.app.chatterlang_serve.compile') as mock_compile:
            mock_compiled = Mock()
            mock_compiled.as_function.return_value = mock_compiled
            mock_compile.return_value = mock_compiled
            
            session.compile_script("| print")
            
            mock_compile.assert_called_once_with("| print")
            assert session.compiled_script == mock_compiled
    
    def test_compile_script_failure(self):
        """Test script compilation failure."""
        session = UserSession("test-session-id")

        # Use actually invalid ChatterLang syntax to trigger a real compilation error
        with pytest.raises(Exception):
            session.compile_script("invalid script syntax")

        assert session.compiled_script is None
    
    def test_add_to_history(self):
        """Test adding entries to history."""
        session = UserSession("test-session-id", history_length=3)
        
        # Add entries within limit
        session.add_to_history({"entry": 1})
        session.add_to_history({"entry": 2})
        assert len(session.history) == 2
        
        # Add more entries to exceed limit
        session.add_to_history({"entry": 3})
        session.add_to_history({"entry": 4})
        
        # Should keep only the last 3 entries
        assert len(session.history) == 3
        assert session.history[0] == {"entry": 2}
        assert session.history[1] == {"entry": 3}
        assert session.history[2] == {"entry": 4}
    
    def test_add_output(self):
        """Test adding output to queue."""
        session = UserSession("test-session-id")
        
        session.add_output("Test output", "response")
        
        # Check if output was added to queue
        output = session.output_queue.get_nowait()
        assert output["output"] == "Test output"
        assert output["type"] == "response"
        assert "timestamp" in output
    
    def test_add_output_queue_full(self):
        """Test adding output when queue is full."""
        session = UserSession("test-session-id")
        
        # Fill the queue
        for i in range(1000):
            try:
                session.output_queue.put(f"item_{i}", block=False)
            except:
                break
        
        # Adding output should not raise an exception
        session.add_output("New output", "response")
    
    def test_update_activity(self):
        """Test updating activity timestamp."""
        session = UserSession("test-session-id")
        original_time = session.last_activity
        
        time.sleep(0.01)  # Small delay
        session.update_activity()
        
        assert session.last_activity > original_time


class TestChatterlangServer:
    """Test ChatterlangServer class."""
    
    @pytest.fixture
    def server_config(self):
        """Basic server configuration."""
        return {
            "host": "localhost",
            "port": 8999,
            "api_key": "test-key",
            "require_auth": False,
            "title": "Test Server"
        }
    
    @pytest.fixture
    def form_config(self):
        """Test form configuration."""
        return {
            "title": "Test Form",
            "fields": [
                {"name": "prompt", "type": "text", "label": "Prompt", "required": True},
                {"name": "count", "type": "number", "label": "Count", "default": 1}
            ],
            "position": "bottom",
            "height": "200px",
            "theme": "dark"
        }
    
    def test_init_default_config(self):
        """Test server initialization with default configuration."""
        server = ChatterlangServer()
        
        assert server.host == "localhost"
        assert server.port == 9999
        assert server.require_auth is False
        assert server.title == "ChatterLang Server"
        assert isinstance(server.form_config, FormConfig)
        assert server.form_config.title == "Data Input Form"
        assert len(server.form_config.fields) == 1
        assert server.form_config.fields[0].name == "prompt"
    
    def test_init_custom_config(self, server_config, form_config):
        """Test server initialization with custom configuration."""
        server = ChatterlangServer(
            **server_config,
            form_config=form_config
        )
        
        assert server.host == server_config["host"]
        assert server.port == server_config["port"]
        assert server.api_key == server_config["api_key"]
        assert server.require_auth == server_config["require_auth"]
        assert server.title == server_config["title"]
        assert server.form_config.title == form_config["title"]
        assert len(server.form_config.fields) == 2
    
    def test_init_with_processor_func(self):
        """Test server initialization with custom processor function."""
        def custom_processor(data, session):
            return f"Custom: {data}"
        
        server = ChatterlangServer(processor_func=custom_processor)
        assert server.processor_function == custom_processor
    
    @patch('threading.Thread')
    def test_start_cleanup_task(self, mock_thread):
        """Test starting cleanup background task."""
        server = ChatterlangServer()
        
        # Verify cleanup thread was started
        mock_thread.assert_called()
        mock_thread_instance = mock_thread.return_value
        mock_thread_instance.start.assert_called()
    
    def test_get_or_create_session_new(self):
        """Test creating a new session."""
        server = ChatterlangServer()
        
        # Mock request and response
        mock_request = Mock()
        mock_request.cookies.get.return_value = None
        mock_response = Mock()
        
        session = server.get_or_create_session(mock_request, mock_response)
        
        assert session.session_id is not None
        assert session.session_id in server.sessions
        mock_response.set_cookie.assert_called_once()
    
    def test_get_or_create_session_existing(self):
        """Test getting existing session."""
        server = ChatterlangServer()
        
        # Create existing session
        session_id = str(uuid.uuid4())
        existing_session = UserSession(session_id)
        server.sessions[session_id] = existing_session
        
        # Mock request with existing session ID
        mock_request = Mock()
        mock_request.cookies.get.return_value = session_id
        mock_response = Mock()
        
        session = server.get_or_create_session(mock_request, mock_response)
        
        assert session == existing_session
        assert session.session_id == session_id
        mock_response.set_cookie.assert_not_called()
    
    def test_cleanup_expired_sessions(self):
        """Test cleaning up expired sessions."""
        server = ChatterlangServer()
        
        # Create sessions with different activity times
        old_session = UserSession("old-session")
        old_session.last_activity = datetime.now() - timedelta(hours=25)
        
        new_session = UserSession("new-session")
        new_session.last_activity = datetime.now()
        
        server.sessions["old-session"] = old_session
        server.sessions["new-session"] = new_session
        
        server.cleanup_expired_sessions(max_age_hours=24)
        
        # Only new session should remain
        assert "old-session" not in server.sessions
        assert "new-session" in server.sessions
    
    def test_get_session_by_id(self):
        """Test getting session by ID."""
        server = ChatterlangServer()
        session = UserSession("test-session")
        server.sessions["test-session"] = session
        
        result = server.get_session_by_id("test-session")
        assert result == session
        
        result = server.get_session_by_id("non-existent")
        assert result is None
    
    def test_default_print_processor(self):
        """Test default processor function."""
        server = ChatterlangServer()
        session = UserSession("test-session")
        
        data = {"test": "data"}
        result = server._default_print_processor(data, session)
        
        assert "Data received:" in result
        assert str(data) in result


class TestChatterlangServerEndpoints:
    """Test ChatterlangServer HTTP endpoints."""
    
    @pytest.fixture
    def server(self):
        """Create test server instance."""
        return ChatterlangServer(
            host="localhost",
            port=8999,
            api_key="test-key",
            require_auth=False
        )
    
    @pytest.fixture
    def client(self, server):
        """Create test client."""
        return TestClient(server.app)
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["port"] == 8999
    
    def test_form_config_endpoint(self, client):
        """Test form configuration endpoint."""
        response = client.get("/form-config")
        assert response.status_code == 200
        
        data = response.json()
        assert data["title"] == "Data Input Form"
        assert "fields" in data
        assert len(data["fields"]) == 1
    
    def test_root_endpoint(self, client):
        """Test root HTML endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        html_content = response.text
        assert "ChatterLang Server" in html_content
        assert "form" in html_content.lower()
    
    def test_stream_endpoint(self, client):
        """Test stream HTML endpoint."""
        response = client.get("/stream")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        html_content = response.text
        assert "ChatterLang Server - Stream" in html_content
        assert "chat-messages" in html_content
    
    def test_favicon_endpoint(self, client):
        """Test favicon endpoint."""
        response = client.get("/favicon.ico")
        # Should return 404 if favicon doesn't exist or the file if it does
        assert response.status_code in [200, 404]
    
    def test_process_endpoint_no_auth(self, client):
        """Test process endpoint without authentication."""
        test_data = {"prompt": "test message"}
        
        response = client.post("/process", json=test_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert data["message"] == "Data processed successfully"
        assert "data" in data
        assert data["data"]["input"] == test_data
    
    def test_process_endpoint_with_auth(self):
        """Test process endpoint with authentication."""
        server = ChatterlangServer(
            require_auth=True,
            api_key="test-secret"
        )
        client = TestClient(server.app)
        
        test_data = {"prompt": "test message"}
        
        # Test without API key
        response = client.post("/process", json=test_data)
        assert response.status_code == 403
        
        # Test with correct API key
        response = client.post(
            "/process",
            json=test_data,
            headers={"X-API-Key": "test-secret"}
        )
        assert response.status_code == 200
        
        # Test with incorrect API key
        response = client.post(
            "/process",
            json=test_data,
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 403
    
    def test_process_endpoint_with_script(self):
        """Test process endpoint with compiled script."""
        # Mock compiled script
        mock_compiled = Mock()
        mock_compiled.return_value = iter(["Script output 1", "Script output 2"])
        
        with patch('talkpipe.app.chatterlang_serve.compile') as mock_compile:
            mock_compile.return_value.as_function.return_value = mock_compiled
            
            server = ChatterlangServer(script_content="| print")
            client = TestClient(server.app)
            
            test_data = {"prompt": "test message"}
            response = client.post("/process", json=test_data)
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]["output"]) == 2
            assert "Script output 1" in data["data"]["output"]
            assert "Script output 2" in data["data"]["output"]
    
    def test_process_endpoint_error(self):
        """Test process endpoint error handling."""
        def error_processor(data, session):
            raise Exception("Test error")
        
        server = ChatterlangServer(processor_func=error_processor)
        # Override the default processor to use our error processor
        server._default_print_processor = error_processor
        client = TestClient(server.app)
        
        test_data = {"prompt": "test message"}
        response = client.post("/process", json=test_data)
        
        # The error should be caught and returned as a 500 status
        assert response.status_code == 500
        assert "Test error" in response.json()["detail"]
    
    def test_history_endpoint(self, client, server):
        """Test history endpoint."""
        # Add some history to a session
        session = UserSession("test-session")
        session.add_to_history({"input": "test1", "output": "response1"})
        session.add_to_history({"input": "test2", "output": "response2"})
        server.sessions["test-session"] = session
        
        # Mock cookies to use existing session
        response = client.get(
            "/history?limit=10",
            cookies={"talkpipe_session_id": "test-session"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["entries"]) == 2
    
    def test_clear_history_endpoint(self, client, server):
        """Test clear history endpoint."""
        # Add history to a session
        session = UserSession("test-session")
        session.add_to_history({"input": "test", "output": "response"})
        server.sessions["test-session"] = session
        
        # Clear history
        response = client.delete(
            "/history",
            cookies={"talkpipe_session_id": "test-session"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(session.history) == 0
    
    def test_output_stream_endpoint_route_exists(self, server):
        """Test that the output stream endpoint route is configured."""
        # Test that the route exists in the FastAPI app routes
        routes = [route.path for route in server.app.routes]
        assert "/output-stream" in routes
        
        # Test the stream generator method exists and is callable
        mock_request = Mock()
        mock_request.cookies.get.return_value = None
        mock_response = Mock()
        session = server.get_or_create_session(mock_request, mock_response)
        stream_generator = server._generate_output_stream(session)
        assert hasattr(stream_generator, '__aiter__')  # It's an async generator


class TestHTMLGeneration:
    """Test HTML interface generation."""
    
    def test_generate_form_fields_text(self):
        """Test generating text form fields."""
        server = ChatterlangServer()
        field = FormField(name="test_field", type="text", label="Test Label", placeholder="Enter text", required=True)
        server.form_config.fields = [field]
        
        html = server._generate_form_fields()
        
        assert 'name="test_field"' in html
        assert 'type="text"' in html
        assert 'Test Label' in html
        assert 'placeholder="Enter text"' in html
        assert 'required' in html
    
    def test_generate_form_fields_select(self):
        """Test generating select form fields."""
        server = ChatterlangServer()
        field = FormField(name="choice", type="select", options=["opt1", "opt2", "opt3"])
        server.form_config.fields = [field]
        
        html = server._generate_form_fields()
        
        assert '<select' in html
        assert 'name="choice"' in html
        assert '<option value="opt1">opt1</option>' in html
        assert '<option value="opt2">opt2</option>' in html
        assert '<option value="opt3">opt3</option>' in html
    
    def test_generate_form_fields_textarea(self):
        """Test generating textarea form fields."""
        server = ChatterlangServer()
        field = FormField(name="description", type="textarea", rows=5, default="Default text")
        server.form_config.fields = [field]
        
        html = server._generate_form_fields()
        
        assert '<textarea' in html
        assert 'name="description"' in html
        assert 'rows="5"' in html
        assert 'Default text' in html
    
    def test_generate_form_fields_checkbox(self):
        """Test generating checkbox form fields."""
        server = ChatterlangServer()
        field = FormField(name="agree", type="checkbox", label="I agree", default=True)
        server.form_config.fields = [field]
        
        html = server._generate_form_fields()
        
        assert 'type="checkbox"' in html
        assert 'name="agree"' in html
        assert 'I agree' in html
        assert 'checked' in html
    
    def test_generate_form_fields_number(self):
        """Test generating number form fields."""
        server = ChatterlangServer()
        field = FormField(name="count", type="number", min=0, max=100, default=50)
        server.form_config.fields = [field]
        
        html = server._generate_form_fields()
        
        assert 'type="number"' in html
        assert 'name="count"' in html
        assert 'min="0"' in html
        assert 'max="100"' in html
        assert 'value="50"' in html
    
    def test_get_html_interface_themes(self):
        """Test HTML interface generation."""
        # The main HTML interface doesn't use theme colors, just test it generates HTML
        server = ChatterlangServer(form_config={"theme": "dark"})
        html = server._get_html_interface()
        assert "<!DOCTYPE html>" in html
        assert "ChatterLang Server" in html
        assert "form" in html.lower()
        
        # Test light theme for stream interface (which does use theme colors)
        server = ChatterlangServer(form_config={"theme": "light"})
        html = server._get_stream_interface()
        assert "#f5f5f5" in html  # Light background color
    
    def test_get_stream_interface_positions(self):
        """Test stream interface with different form positions."""
        positions = ["bottom", "top", "left", "right"]
        
        for position in positions:
            server = ChatterlangServer(form_config={"position": position})
            html = server._get_stream_interface()
            
            assert f"form-panel" in html
            # Each position should have specific CSS styling
            assert "flex-direction:" in html or "order:" in html


class TestChatterlangServerSegment:
    """Test ChatterlangServerSegment class."""
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    def test_init(self, mock_server_class):
        """Test segment initialization."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        segment = ChatterlangServerSegment(
            port=8888,
            host="127.0.0.1",
            api_key="test-key",
            require_auth=True
        )
        
        assert segment.port == 8888
        assert segment.host == "127.0.0.1"
        assert segment.api_key == "test-key"
        assert segment.require_auth is True
        assert isinstance(segment.queue, Queue)
        
        # Verify server was created and started
        mock_server_class.assert_called_once()
        mock_server.start.assert_called_once_with(background=True)
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    def test_init_with_form_config_dict(self, mock_server_class):
        """Test segment initialization with form config dictionary."""
        form_config = {"title": "Test Form", "fields": []}
        
        segment = ChatterlangServerSegment(form_config=form_config)
        
        # Verify form config was passed to server
        call_args = mock_server_class.call_args[1]
        assert call_args["form_config"] == form_config
    
    @patch('talkpipe.app.chatterlang_serve.get_config')
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    def test_init_with_form_config_variable(self, mock_server_class, mock_get_config):
        """Test segment initialization with form config from variable."""
        form_config_data = {"title": "Config Form"}
        mock_get_config.return_value = json.dumps(form_config_data)
        
        segment = ChatterlangServerSegment(form_config="$FORM_CONFIG")
        
        mock_get_config.assert_called_once_with("FORM_CONFIG")
    
    def test_process_data(self):
        """Test processing incoming data."""
        with patch('talkpipe.app.chatterlang_serve.ChatterlangServer'):
            segment = ChatterlangServerSegment()
            
            test_data = {"prompt": "test message"}
            result = segment.process_data(test_data)
            
            # Check data was queued
            queued_data = segment.queue.get_nowait()
            assert queued_data == test_data
            
            # Check return value
            assert "Data received and queued:" in result
            assert str(test_data) in result
    
    def test_process_data_error(self):
        """Test processing data with queue error."""
        with patch('talkpipe.app.chatterlang_serve.ChatterlangServer'):
            segment = ChatterlangServerSegment()
            
            # Mock the queue.put method to raise an exception
            segment.queue.put = Mock(side_effect=Exception("Queue error"))
            
            test_data = {"prompt": "test message"}
            result = segment.process_data(test_data)
            
            assert "Error processing data:" in result
            assert "Queue error" in result
    
    def test_generate(self):
        """Test data generation from queue."""
        with patch('talkpipe.app.chatterlang_serve.ChatterlangServer'):
            segment = ChatterlangServerSegment()
            
            # Add test data to queue
            test_data = {"prompt": "test message"}
            segment.queue.put(test_data)
            
            # Get generator
            generator = segment.generate()
            
            # Get first item
            result = next(generator)
            assert result == test_data


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_load_form_config_yaml(self):
        """Test loading form configuration from YAML file."""
        config_data = {
            "title": "Test Form",
            "fields": [
                {"name": "prompt", "type": "text", "required": True}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config_data, f)
            temp_file = f.name
        
        try:
            result = load_form_config(temp_file)
            assert result["title"] == "Test Form"
            assert len(result["fields"]) == 1
            assert result["fields"][0]["name"] == "prompt"
        finally:
            import os
            os.unlink(temp_file)
    
    def test_load_form_config_json(self):
        """Test loading form configuration from JSON file."""
        config_data = {
            "title": "Test Form",
            "fields": [
                {"name": "prompt", "type": "text", "required": True}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_file = f.name
        
        try:
            result = load_form_config(temp_file)
            assert result["title"] == "Test Form"
            assert len(result["fields"]) == 1
            assert result["fields"][0]["name"] == "prompt"
        finally:
            import os
            os.unlink(temp_file)
    
    def test_load_form_config_file_not_found(self):
        """Test loading form configuration with non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_form_config("/non/existent/file.yaml")
    
    def test_load_form_config_unsupported_format(self):
        """Test loading form configuration with unsupported format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("test content")
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="Unsupported configuration file format"):
                load_form_config(temp_file)
        finally:
            import os
            os.unlink(temp_file)


class TestMainFunction:
    """Test main entry point function."""
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('sys.argv', ['script.py'])
    def test_go_default_args(self, mock_server_class):
        """Test go function with default arguments."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'), \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):
            
            go()
            
            # Verify server was created with default values
            mock_server_class.assert_called_once()
            call_args = mock_server_class.call_args[1]
            assert call_args["host"] == "localhost"
            assert call_args["port"] == 2025
            assert call_args["require_auth"] is False
            
            # Verify server was started
            mock_server.start.assert_called_once_with(background=False)
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('sys.argv', [
        'script.py', '--port', '8888', '--host', '127.0.0.1', 
        '--api-key', 'secret', '--require-auth', '--title', 'Custom Server'
    ])
    def test_go_custom_args(self, mock_server_class):
        """Test go function with custom arguments."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'), \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):
            
            go()
            
            # Verify server was created with custom values
            call_args = mock_server_class.call_args[1]
            assert call_args["host"] == "127.0.0.1"
            assert call_args["port"] == 8888
            assert call_args["api_key"] == "secret"
            assert call_args["require_auth"] is True
            assert call_args["title"] == "Custom Server"
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('talkpipe.app.chatterlang_serve.load_script')
    @patch('sys.argv', ['script.py', '--script', 'test_script.cl'])
    def test_go_with_script(self, mock_load_script, mock_server_class):
        """Test go function with script loading."""
        mock_load_script.return_value = "test script content"
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'):
            
            go()
            
            mock_load_script.assert_called_once_with('test_script.cl')
            
            # Verify script content was passed to server
            call_args = mock_server_class.call_args[1]
            assert call_args["script_content"] == "test script content"
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('talkpipe.app.chatterlang_serve.load_form_config')
    @patch('sys.argv', ['script.py', '--form-config', 'config.yaml'])
    def test_go_with_form_config(self, mock_load_form_config, mock_server_class):
        """Test go function with form configuration."""
        form_config_data = {"title": "Test Form"}
        mock_load_form_config.return_value = form_config_data
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'), \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):
            
            go()
            
            mock_load_form_config.assert_called_once_with('config.yaml')
            
            # Verify form config was passed to server
            call_args = mock_server_class.call_args[1]
            assert call_args["form_config"] == form_config_data
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('talkpipe.app.chatterlang_serve.load_module_file')
    @patch('sys.argv', ['script.py', '--load-module', 'module1.py', '--load-module', 'module2.py'])
    def test_go_with_modules(self, mock_load_module, mock_server_class):
        """Test go function with module loading."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'), \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):
            
            go()
            
            # Verify modules were loaded
            assert mock_load_module.call_count == 2
            mock_load_module.assert_any_call(fname='module1.py', fail_on_missing=False)
            mock_load_module.assert_any_call(fname='module2.py', fail_on_missing=False)
    
    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('sys.argv', ['script.py', '--CUSTOM_VAR', 'custom_value', '--ANOTHER_VAR', '123'])
    def test_go_with_constants(self, mock_server_class):
        """Test go function with custom constants."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server
        
        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args') as mock_parse_args, \
             patch('talkpipe.app.chatterlang_serve.add_config_values') as mock_add_config, \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):
            
            # Mock parsing of unknown arguments
            mock_parse_args.return_value = {
                'CUSTOM_VAR': 'custom_value',
                'ANOTHER_VAR': '123'
            }
            
            go()
            
            # Verify constants were added to config
            mock_add_config.assert_called_once_with(
                {'CUSTOM_VAR': 'custom_value', 'ANOTHER_VAR': '123'},
                override=True
            )

    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('talkpipe.app.chatterlang_serve.get_config')
    @patch('sys.argv', ['script.py'])
    def test_go_api_key_from_config(self, mock_get_config, mock_server_class):
        """Test go function loads API key from configuration when not provided on command line."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        # Mock configuration with API_KEY
        mock_config = {'API_KEY': 'config-api-key'}
        mock_get_config.return_value = mock_config

        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'), \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):

            go()

            # Verify server was created with API key from config
            call_args = mock_server_class.call_args[1]
            assert call_args["api_key"] == "config-api-key"

    @patch('talkpipe.app.chatterlang_serve.ChatterlangServer')
    @patch('talkpipe.app.chatterlang_serve.get_config')
    @patch('sys.argv', ['script.py', '--api-key', 'cmdline-api-key'])
    def test_go_api_key_cmdline_overrides_config(self, mock_get_config, mock_server_class):
        """Test go function uses command line API key over configuration."""
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        # Mock configuration with API_KEY
        mock_config = {'API_KEY': 'config-api-key'}
        mock_get_config.return_value = mock_config

        with patch('talkpipe.app.chatterlang_serve.parse_unknown_args', return_value={}), \
             patch('talkpipe.app.chatterlang_serve.add_config_values'), \
             patch('talkpipe.app.chatterlang_serve.load_script', return_value=None):

            go()

            # Verify server was created with command line API key (takes precedence)
            call_args = mock_server_class.call_args[1]
            assert call_args["api_key"] == "cmdline-api-key"


class TestAsyncFunctionality:
    """Test async functionality."""
    
    def test_process_json_success(self):
        """Test JSON processing (sync version)."""
        server = ChatterlangServer()
        session = UserSession("test-session")
        
        test_data = {"prompt": "test message"}
        # Use asyncio.run to test the async function
        import asyncio
        result = asyncio.run(server._process_json(test_data, session))
        
        assert isinstance(result, DataResponse)
        assert result.status == "success"
        assert result.data["input"] == test_data
    
    def test_process_json_with_iterable_result(self):
        """Test JSON processing with iterable result."""
        def mock_processor(data, session):
            return iter(["output1", "output2", "output3"])
        
        server = ChatterlangServer(processor_func=mock_processor)
        # Override the default processor to use our mock processor
        server._default_print_processor = mock_processor
        session = UserSession("test-session")
        
        test_data = {"prompt": "test message"}
        import asyncio
        result = asyncio.run(server._process_json(test_data, session))
        
        assert result.status == "success"
        assert len(result.data["output"]) == 3
        assert "output1" in result.data["output"]
        assert "output2" in result.data["output"]
        assert "output3" in result.data["output"]
    
    def test_process_json_with_compiled_script(self):
        """Test JSON processing with compiled script."""
        mock_compiled = Mock()
        mock_compiled.return_value = iter(["script output"])
        
        session = UserSession("test-session")
        session.compiled_script = mock_compiled
        
        server = ChatterlangServer()
        
        test_data = {"prompt": "test message"}
        import asyncio
        result = asyncio.run(server._process_json(test_data, session))
        
        mock_compiled.assert_called_once_with(test_data)
        assert result.status == "success"
        assert "script output" in result.data["output"]