import pytest
from talkpipe.jupyter.interactive import InteractiveChatterLangWidget

def test_interactive_widget_initialization():
    """Test that the interactive widget initializes correctly."""
    # Default initialization
    widget = InteractiveChatterLangWidget()
    assert widget.script_editor.value == ""
    assert widget.last_results is None
    assert widget.is_interactive is False
    assert widget.compiled_script is None
    assert widget.interactive_row.layout.display == 'none'
    assert widget.interactive_input.disabled is True
    
    # Custom initialization
    test_script = "| llmPrompt[name='test']"
    widget = InteractiveChatterLangWidget(initial_script=test_script, height="400px")
    assert widget.script_editor.value == test_script
    assert widget.script_editor.layout.height == "400px"

def test_run_interactive_script(monkeypatch):
    """Test running an interactive script."""
    # Set up mock compiler
    def mock_compile(script):
        return lambda x=None: []
    
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", mock_compile)
    
    # Create widget with an interactive script (starts with |)
    widget = InteractiveChatterLangWidget(initial_script="| llmPrompt[name='test']")
    widget._run_script(None)
    
    # Assertions for interactive mode
    assert widget.is_interactive is True
    assert widget.interactive_row.layout.display == 'flex'
    assert widget.interactive_input.disabled is False
    assert widget.submit_button.disabled is False
    assert "green" in widget.status.value  # Ready status

def test_run_non_interactive_script(monkeypatch):
    """Test running a non-interactive script."""
    # Set up mock with results
    results = ["Result 1", "Result 2"]
    
    def mock_pipeline():
        return results
    
    def mock_compile(script):
        return lambda x=None: mock_pipeline()
    
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", mock_compile)
    
    # Create widget with a non-interactive script
    widget = InteractiveChatterLangWidget(initial_script="INPUT FROM echo[data='test'] | print")
    widget._run_script(None)
    
    # Assertions for non-interactive mode
    assert widget.is_interactive is False
    assert widget.interactive_row.layout.display == 'none'
    assert widget.interactive_input.disabled is True
    assert widget.submit_button.disabled is True
    assert widget.last_results == results
    assert "green" in widget.status.value  # Success status

def test_submit_interactive_input(monkeypatch):
    """Test submitting input in interactive mode."""
    # Set up mock for interactive script
    response = ["Response to input"]
    
    def mock_compiled_script(input_text):
        return response
    
    # Create widget and setup for test
    widget = InteractiveChatterLangWidget()
    widget.is_interactive = True
    widget.compiled_script = mock_compiled_script
    widget.interactive_input.value = "Test input"
    
    # Submit input
    widget._submit_input(None)
    
    # Assertions
    assert widget.last_results == response
    assert widget.interactive_input.value == ""  # Input field cleared
    assert "green" in widget.status.value  # Success status

def test_interactive_script_error(monkeypatch):
    """Test error handling in interactive script."""
    # Set up mock to raise exception
    def mock_compile(script):
        raise ValueError("Test error")
    
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", mock_compile)
    
    # Create widget and run script
    widget = InteractiveChatterLangWidget(initial_script="| invalid script")
    widget._run_script(None)
    
    # Assertions
    assert widget.is_interactive is False
    assert widget.interactive_row.layout.display == 'none'
    assert widget.interactive_input.disabled is True
    assert widget.submit_button.disabled is True
    assert "red" in widget.status.value  # Error status

def test_input_submit_event(monkeypatch):
    """Test the Enter key handling in input field."""
    # Create a mock for the submit function
    was_called = False
    
    def mock_submit_input(button):
        nonlocal was_called
        was_called = True
    
    # Create widget and patch the submit method
    widget = InteractiveChatterLangWidget()
    monkeypatch.setattr(widget, "_submit_input", mock_submit_input)
    
    # Trigger the event
    widget._on_input_submit(None)
    
    # Check that the submit function was called
    assert was_called is True