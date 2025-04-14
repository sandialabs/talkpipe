import pytest
from talkpipe.jupyter.examples import ChatterLangWidgetWithExamples, EXAMPLE_SCRIPTS

def test_examples_widget_initialization():
    """Test that the examples widget initializes correctly."""
    widget = ChatterLangWidgetWithExamples()
    assert widget.script_editor.value == ""
    # Check that example categories are loaded
    assert set(widget.example_categories.options) == set(EXAMPLE_SCRIPTS.keys())
    # Check that example selector is populated
    assert len(widget.example_selector.options) > 0

def test_update_examples():
    """Test that changing categories updates examples."""
    widget = ChatterLangWidgetWithExamples()
    
    # Get initial examples count
    initial_category = widget.example_categories.value
    initial_count = len(widget.example_selector.options)
    
    # Switch to a different category
    different_category = [cat for cat in EXAMPLE_SCRIPTS.keys() if cat != initial_category][0]
    widget.example_categories.value = different_category
    widget._update_examples(None)  # Manually trigger update
    
    # Count should probably be different (depends on EXAMPLE_SCRIPTS content)
    assert len(widget.example_selector.options) == len(EXAMPLE_SCRIPTS[different_category])

def test_load_example():
    """Test loading an example into the editor."""
    widget = ChatterLangWidgetWithExamples()
    
    # Select first category and example
    category = widget.example_categories.value
    widget.example_selector.value = 0  # First example
    
    # Load the example
    widget._load_example(None)
    
    # Check that the script is loaded
    expected_code = EXAMPLE_SCRIPTS[category][0]["code"]
    assert widget.script_editor.value == expected_code
    assert "blue" in widget.status.value  # Loaded status

def test_run_example(monkeypatch):
    """Test running an example script."""
    # Set up mock with results
    results = ["Example result"]
    
    def mock_pipeline():
        return results
    
    def mock_compile(script):
        return lambda x=None: mock_pipeline()
    
    monkeypatch.setattr("talkpipe.chatterlang.compiler.compile", mock_compile)
    
    # Create widget and load an example
    widget = ChatterLangWidgetWithExamples()
    category = widget.example_categories.value
    widget.example_selector.value = 0  # First example
    widget._load_example(None)
    
    # Run the example
    widget._run_script(None)
    
    # Assertions
    assert widget.last_results == results
    assert "green" in widget.status.value  # Success status