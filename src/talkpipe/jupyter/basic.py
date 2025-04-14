import ipywidgets as widgets
from IPython.display import display, clear_output
import sys
import traceback
from talkpipe.chatterlang import compiler

class ChatterLangWidget:
    """A widget for executing ChatterLang scripts in Jupyter notebooks."""
    
    def __init__(self, initial_script="", height="300px"):
        """Initialize the ChatterLang widget."""
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
                min_height='100px'  # Ensure output area is visible
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
        
        # Explicitly attach event handlers
        self.run_button.on_click(self._run_script)
        self.clear_button.on_click(self._clear_output)
        
        # Layout the widget
        buttons = widgets.HBox([self.run_button, self.clear_button, self.show_full_error])
        self.widget = widgets.VBox([
            self.script_editor,
            buttons,
            self.status,
            self.output_area
        ])
    
    def _run_script(self, button):
        """Execute the ChatterLang script."""
        # Clear previous output and results
        self.last_results = None
        
        with self.output_area:
            clear_output(wait=True)
        
        script = self.script_editor.value.strip()
        if not script:
            self.status.value = '<span style="color:orange;">Error: Script is empty</span>'
            return
        
        self.status.value = '<span style="color:blue;">Running...</span>'
        
        with self.output_area:
            try:
                print("Compiling script...")
                # Compile the script
                pipeline = compiler.compile(script)
                print("Script compiled successfully!")
                
                # Execute the pipeline
                print("\n--- Executing pipeline ---")
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
            clear_output(wait=True)
            print("Output cleared.")  # Add a confirmation message
        self.status.value = '<span style="color:gray;">Output cleared</span>'

    def display(self):
        """Display the widget."""
        display(self.widget)