import ipywidgets as widgets
from IPython.display import display, clear_output, Javascript, HTML
import sys
import traceback
from talkpipe.chatterlang import compiler

class InteractiveChatterLangWidget:
    """A widget for executing interactive ChatterLang scripts in Jupyter notebooks."""
    
    def __init__(self, initial_script="", height="300px"):
        """Initialize the interactive ChatterLang widget.
        
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
        
        # Create output area with unique ID for scrolling
        self.output_area = widgets.Output(
            layout=widgets.Layout(
                width='100%',
                border='1px solid #ddd',
                padding='10px',
                overflow='auto',
                max_height='300px'
            )
        )
        self.output_area_id = f"output-{id(self)}"
        self.output_area._dom_classes = [self.output_area_id]
        
        # Status message
        self.status = widgets.HTML(
            value='<span style="color:gray;">Ready</span>',
            layout=widgets.Layout(width='100%', margin='5px 0')
        )
        
        # Interactive input
        self.interactive_input = widgets.Text(
            value='',
            placeholder='Enter input for interactive script...',
            description='Input:',
            disabled=True,
            layout=widgets.Layout(width='80%')
        )
        
        # Interactive submit button
        self.submit_button = widgets.Button(
            description='Submit',
            button_style='info',
            tooltip='Submit input to running script',
            icon='check',
            disabled=True,
            layout=widgets.Layout(width='20%')
        )
        
        # Create interactive input row
        self.interactive_row = widgets.HBox([
            self.interactive_input,
            self.submit_button
        ])
        self.interactive_row.layout.display = 'none'
        
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
        
        # Instance variables for interactive mode
        self.compiled_script = None
        self.is_interactive = False
        
        # Attach event handlers
        self.run_button.on_click(self._run_script)
        self.clear_button.on_click(self._clear_output)
        self.submit_button.on_click(self._submit_input)
        self.interactive_input.on_submit(self._on_input_submit)
        
        # Layout the widget
        buttons = widgets.HBox([self.run_button, self.clear_button, self.show_full_error])
        self.widget = widgets.VBox([
            self.script_editor,
            buttons,
            self.status,
            self.interactive_row,
            self.output_area
        ])
    
    def _run_script(self, button):
        """Execute the ChatterLang script."""
        # Reset results
        self.last_results = None
        
        script = self.script_editor.value.strip()
        if not script:
            self.status.value = '<span style="color:orange;">Error: Script is empty</span>'
            return
        
        self.status.value = '<span style="color:blue;">Compiling script...</span>'
        
        with self.output_area:
            clear_output(wait=True)
            try:
                # Compile the script
                self.compiled_script = compiler.compile(script)
                print("Script compiled successfully")
                
                # Check if this is an interactive script
                # Interactive scripts in ChatterLang typically start with '|'
                for line in script.splitlines():
                    line = line.strip()
                    if not line or line.startswith('CONST') or line.startswith('#'):
                        continue
                    self.is_interactive = line[0] == '|'
                    break
                
                if self.is_interactive:
                    # Enable interactive inputs
                    self.interactive_row.layout.display = 'flex'
                    self.interactive_input.disabled = False
                    self.submit_button.disabled = False
                    self.status.value = '<span style="color:green;">Interactive script ready. Enter input below.</span>'
                    self.interactive_input.focus()
                else:
                    # Execute non-interactive script
                    self.status.value = '<span style="color:blue;">Running non-interactive script...</span>'
                    results = list(self.compiled_script())
                    self.last_results = results
                    
                    # Display results
                    print("\n--- Results ---")
                    for i, result in enumerate(results):
                        print(f"Result {i+1}:", result)
                    
                    self.status.value = '<span style="color:green;">Execution completed successfully</span>'
                    
                    # Reset interactive controls
                    self.interactive_row.layout.display = 'none'
                    self.interactive_input.disabled = True
                    self.submit_button.disabled = True
                
                # Scroll to bottom
                self._scroll_to_bottom()
            
            except Exception as e:
                error_message = f"Error: {str(e)}"
                print(error_message)
                
                if self.show_full_error.value:
                    print("\n--- Traceback ---")
                    traceback.print_exc(file=sys.stdout)
                
                self.status.value = f'<span style="color:red;">Execution failed: {str(e)}</span>'
                
                # Reset interactive controls
                self.interactive_row.layout.display = 'none'
                self.interactive_input.disabled = True
                self.submit_button.disabled = True
                self.is_interactive = False
                
                # Scroll to bottom to show error
                self._scroll_to_bottom()
    
    def _on_input_submit(self, widget):
        """Handle Enter key pressed in input field."""
        self._submit_input(None)
    
    def _submit_input(self, button):
        """Process interactive input."""
        if not self.is_interactive or self.compiled_script is None:
            return
        
        user_input = self.interactive_input.value
        self.interactive_input.value = ''  # Clear input field
        
        with self.output_area:
            print(f"\n> {user_input}")  # Echo user input
            
            try:
                # Send input to the script
                results = list(self.compiled_script([user_input]))
                self.last_results = results
                
                # Display results
                for result in results:
                    print(result)
                
                self.status.value = '<span style="color:green;">Input processed. Enter next input or re-run the script.</span>'
                
            except Exception as e:
                error_message = f"Error processing input: {str(e)}"
                print(error_message)
                
                if self.show_full_error.value:
                    print("\n--- Traceback ---")
                    traceback.print_exc(file=sys.stdout)
                
                self.status.value = f'<span style="color:red;">Error processing input: {str(e)}</span>'
        
        # Scroll to the bottom of the output area
        self._scroll_to_bottom()
        
        # Re-focus input field
        self.interactive_input.focus()
    
    def _clear_output(self, button):
        """Clear the output area."""
        with self.output_area:
            clear_output(wait=True)
            print("Output cleared.")  # Add a confirmation message
        self.status.value = '<span style="color:gray;">Output cleared</span>'
    
    def _scroll_to_bottom(self):
        """Aggressive scroll to bottom implementation for JupyterLab."""
        # Use multiple approaches with different timing to ensure scrolling works
        for delay in [50, 150, 500]:  # Try multiple delays to catch different rendering timings
            js_code = f"""
            setTimeout(function() {{
                // Target every possible output container in JupyterLab
                var containers = [
                    // Main output containers
                    document.querySelectorAll('.jp-OutputArea-output'),
                    document.querySelectorAll('.jp-RenderedText'),
                    document.querySelectorAll('.jp-OutputArea-child'),
                    document.querySelectorAll('.output'),
                    document.querySelectorAll('.output_subarea'),
                    document.querySelectorAll('.widget-output'),
                    document.querySelectorAll('.jupyter-widgets-output-area'),
                    // Our specific class
                    document.getElementsByClassName('{self.output_area_id}'),
                    // General scroll containers
                    document.querySelectorAll('[class*="scroll"]'),
                    document.querySelectorAll('[class*="output"]')
                ];

                // Loop through all potential containers and try to scroll them
                containers.forEach(function(elements) {{
                    for (var i = 0; i < elements.length; i++) {{
                        if (elements[i]) {{
                            // Force scroll to bottom 
                            elements[i].scrollTop = 999999; // Use large number to ensure reaching bottom
                            
                            // Also try to scroll any parent elements that might be scrollable
                            let parent = elements[i].parentElement;
                            for (let j = 0; j < 5; j++) {{ // Try more parent levels
                                if (parent) {{
                                    parent.scrollTop = 999999;
                                    parent = parent.parentElement;
                                }}
                            }}
                        }}
                    }}
                }});

                // Find the most recently active output
                var activeOutputs = document.querySelectorAll('.jp-OutputArea.jp-mod-active .jp-OutputArea-output');
                for (var i = 0; i < activeOutputs.length; i++) {{
                    activeOutputs[i].scrollTop = activeOutputs[i].scrollHeight;
                }}

                // Look for our specific output widget using direct DOM traversal
                try {{
                    var allWidgets = document.querySelectorAll('.widget-output');
                    var lastWidget = allWidgets[allWidgets.length - 1];
                    if (lastWidget) {{
                        lastWidget.scrollTop = lastWidget.scrollHeight;
                    }}
                }} catch(e) {{
                    console.log("Error finding widgets:", e);
                }}
            }}, {delay});
            """
            
            display(Javascript(js_code))
    
    def get_results(self):
        """Return the most recent results from script execution."""
        return self.last_results
    
    def display(self):
        """Display the widget."""
        display(self.widget)