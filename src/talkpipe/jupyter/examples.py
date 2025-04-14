import ipywidgets as widgets
from IPython.display import display, clear_output
import sys
import traceback
from talkpipe.chatterlang import compiler

# Example scripts organized by category
EXAMPLE_SCRIPTS = {
    "Basic Examples": [
        {
            "name": "Hello World",
            "description": "Simple example to print a message",
            "code": 'INPUT FROM echo[data="Hello, ChatterLang World!"] | print'
        },
        {
            "name": "Data Transformation",
            "description": "Convert strings to integers",
            "code": 'INPUT FROM echo[data="1|2|hello|3", delimiter="|"] | cast[cast_type="int"] | print'
        },
        {
            "name": "Using Variables",
            "description": "Store data in a variable and reuse it",
            "code": 'INPUT FROM echo[data="1,2,3,4,5"] | @numbers; INPUT FROM @numbers | print'
        }
    ],
    "Data Processing": [
        {
            "name": "Data Scaling",
            "description": "Multiply numeric values by a factor",
            "code": 'INPUT FROM echo[data="1,2,3,4,5"] | cast[cast_type="int"] | scale[multiplier=2] | print'
        },
        {
            "name": "Filtering Data",
            "description": "Filter values greater than a threshold",
            "code": 'INPUT FROM echo[data="1,5,3,8,2"] | cast[cast_type="int"] | gt[field="_", n=3] | print'
        },
        {
            "name": "Processing Loop",
            "description": "Process data in multiple iterations",
            "code": 'INPUT FROM range[lower=0, upper=5] | @data;\nLOOP 3 TIMES {\n    INPUT FROM @data | scale[multiplier=2] | @data\n};\nINPUT FROM @data | print'
        }
    ],
    "Advanced Features": [
        {
            "name": "JSON Processing",
            "description": "Process JSON data",
            "code": '| loadsJsonl | toDataFrame'
        },
        {
            "name": "Fork Operation",
            "description": "Process data through multiple branches",
            "code": 'INPUT FROM range[lower=0, upper=3] | fork(scale[multiplier=2], scale[multiplier=3]) | print'
        }
    ]
}

class ChatterLangWidgetWithExamples:
    """A widget for executing ChatterLang scripts with example library."""
    
    def __init__(self, initial_script="", height="300px"):
        """Initialize the ChatterLang widget.
        
        Args:
            initial_script (str): Initial script content
            height (str): Height of the script editor
        """
        # Store the most recent results
        self.last_results = None
        
        # Create textarea for script input
        self.script_editor = widgets.Textarea(
            value=initial_script,
            placeholder='Enter your ChatterLang script here...',
            description='Script:',
            disabled=False,
            layout=widgets.Layout(width='100%', height=height)
        )
        
        # Create output area
        self.output_area = widgets.Output(
            layout=widgets.Layout(
                width='100%',
                border='1px solid #ddd',
                padding='10px',
                overflow='auto',
                max_height='400px'
            )
        )
        
        # Status message
        self.status = widgets.HTML(
            value='<span style="color:gray;">Ready</span>',
            layout=widgets.Layout(width='100%', margin='5px 0')
        )
        
        # Create buttons
        self.run_button = widgets.Button(
            description='Run Script',
            button_style='primary',
            tooltip='Execute the ChatterLang script',
            icon='play',
            layout=widgets.Layout(width='150px')
        )
        
        self.clear_button = widgets.Button(
            description='Clear Output',
            button_style='',
            tooltip='Clear the output area',
            icon='trash',
            layout=widgets.Layout(width='150px')
        )
        
        # Create a checkbox for showing full errors
        self.show_full_error = widgets.Checkbox(
            value=False,
            description='Show full errors',
            indent=False
        )
        
        # Create example dropdown
        self.example_categories = widgets.Dropdown(
            options=list(EXAMPLE_SCRIPTS.keys()),
            description='Category:',
            disabled=False,
        )
        
        # Create example selector (initially empty)
        self.example_selector = widgets.Dropdown(
            options=[],
            description='Example:',
            disabled=False,
        )
        
        # Create load example button
        self.load_example_button = widgets.Button(
            description='Load Example',
            tooltip='Load the selected example into the editor',
            icon='copy',
            layout=widgets.Layout(width='150px')
        )
        
        # Populate example selector based on initial category
        self._update_examples(None)
        
        # Attach event handlers
        self.run_button.on_click(self._run_script)
        self.clear_button.on_click(self._clear_output)
        self.example_categories.observe(self._update_examples, names='value')
        self.load_example_button.on_click(self._load_example)
        
        # Create accordion for examples section
        examples_box = widgets.VBox([
            widgets.HBox([self.example_categories, self.example_selector]),
            self.load_example_button
        ])
        examples_accordion = widgets.Accordion(children=[examples_box])
        examples_accordion.set_title(0, 'Example Library')
        
        # Layout the widget
        buttons = widgets.HBox([self.run_button, self.clear_button, self.show_full_error])
        self.widget = widgets.VBox([
            examples_accordion,
            self.script_editor,
            buttons,
            self.status,
            self.output_area
        ])
    
    def _update_examples(self, change):
        """Update the example selector when category changes."""
        category = self.example_categories.value
        
        # Get examples for selected category
        examples_in_category = EXAMPLE_SCRIPTS.get(category, [])
        
        # Update example selector options
        self.example_selector.options = [
            (f"{ex['name']}: {ex['description']}", i) 
            for i, ex in enumerate(examples_in_category)
        ]
    
    def _load_example(self, button):
        """Load the selected example into the script editor."""
        category = self.example_categories.value
        example_idx = self.example_selector.value
        
        if example_idx is not None:
            example = EXAMPLE_SCRIPTS[category][example_idx]
            self.script_editor.value = example["code"]
            self.status.value = f'<span style="color:blue;">Loaded example: {example["name"]}</span>'
    
    def _run_script(self, button):
        """Execute the ChatterLang script."""
        # Reset results
        self.last_results = None
        
        script = self.script_editor.value.strip()
        if not script:
            self.status.value = '<span style="color:orange;">Error: Script is empty</span>'
            return
        
        self.status.value = '<span style="color:blue;">Running...</span>'
        
        with self.output_area:
            clear_output()
            try:
                # Compile the script
                pipeline = compiler.compile(script)
                print("Script compiled successfully")
                
                # Execute the pipeline
                print("\n--- Output ---")
                results = list(pipeline())
                
                # Store results for later access
                self.last_results = results
                
                # Display results
                print("\n--- Results ---")
                for i, result in enumerate(results):
                    print(f"Result {i+1}:", result)
                
                self.status.value = '<span style="color:green;">Execution completed successfully</span>'
            
            except Exception as e:
                error_message = f"Error: {str(e)}"
                print(error_message)
                
                if self.show_full_error.value:
                    print("\n--- Traceback ---")
                    traceback.print_exc(file=sys.stdout)
                
                self.status.value = f'<span style="color:red;">Execution failed: {str(e)}</span>'
    
    def get_results(self):
        """Return the most recent results from script execution."""
        return self.last_results
        
    def _clear_output(self, button):
        """Clear the output area."""
        with self.output_area:
            clear_output()
            print("Output cleared.")  # Add a confirmation message
        self.status.value = '<span style="color:gray;">Output cleared</span>'

    def display(self):
        """Display the widget."""
        display(self.widget)