import pytest
from talkpipe.jupyter.basic import ChatterLangWidget

def test_chatterlang_widget_initialization():
    """Test that the widget initializes correctly with default and custom values."""
    # Default initialization
    widget = ChatterLangWidget()
    assert widget.script_editor.value == ""
    assert widget.last_results is None
    
    # Custom initialization
    test_script = "INPUT FROM echo[data='test'] | print"
    widget = ChatterLangWidget(initial_script=test_script, height="400px")
    assert widget.script_editor.value == test_script
    assert widget.script_editor.layout.height == "400px"

def test_run_script_success(monkeypatch):
    """Test successful script execution."""
    # Set up mock pipeline
    results = ["Result 1", "Result 2"]
    
    def mock_pipeline():
        return results
    
    def mock_compile(script):
        return lambda x=None: mock_pipeline()
    
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", mock_compile)
    
    # Create widget and run script
    widget = ChatterLangWidget(initial_script="INPUT FROM echo[data='test'] | print")
    widget._run_script(None)  # Button argument is None in test
    
    # Assertions
    assert widget.last_results == results
    assert "green" in widget.status.value  # Success status

def test_run_script_error(monkeypatch):
    """Test script execution with error."""
    def mock_compile(script):
        raise ValueError("Test error")
    
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", mock_compile)
    
    # Create widget and run script
    widget = ChatterLangWidget(initial_script="Invalid script")
    widget._run_script(None)
    
    # Assertions
    assert widget.last_results is None
    assert "red" in widget.status.value  # Error status

def test_run_empty_script():
    """Test attempting to run an empty script."""
    widget = ChatterLangWidget()
    widget._run_script(None)
    
    assert "orange" in widget.status.value  # Warning status
    assert "empty" in widget.status.value.lower()

def test_clear_output():
    """Test clearing the output area."""
    widget = ChatterLangWidget()
    widget._clear_output(None)
    
    assert "gray" in widget.status.value  # Neutral status
    assert "cleared" in widget.status.value.lower()

def test_get_results():
    """Test getting results from the widget."""
    widget = ChatterLangWidget()
    widget.last_results = ["test result"]
    
    assert widget.get_results() == ["test result"]