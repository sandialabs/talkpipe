#!/usr/bin/env python3
"""
TalkPipe Documentation Browser

A terminal-based interactive browser for TalkPipe documentation.
Allows browsing packages, searching for components, and viewing detailed documentation.
Uses plugin introspection to load live component information.
"""

from typing import Dict, List
import argparse
import sys
from talkpipe.chatterlang.registry import input_registry, segment_registry
from talkpipe.util.plugin_loader import load_plugins
from talkpipe.util.doc_extraction import (
    extract_component_info, detect_component_type, extract_parameters_dict
)

class TalkPipeDoc:
    """Represents a single TalkPipe component (class or function)."""

    def __init__(self, name: str, chatterlang_names: List[str], doc_type: str,
                 module: str, base_classes: List[str], docstring: str,
                 parameters: Dict[str, str]):
        self.name = name
        self.chatterlang_names = chatterlang_names  # List of all names for this component
        self.primary_name = chatterlang_names[0]  # Primary name for display
        self.doc_type = doc_type  # 'Source', 'Segment', 'Field Segment'
        self.module = module
        self.base_classes = base_classes
        self.docstring = docstring
        self.parameters = parameters

    @property
    def chatterlang_name(self):
        """Backward compatibility property."""
        return self.primary_name

    @property
    def all_names_display(self):
        """Display string showing all names."""
        return ", ".join(self.chatterlang_names)


class TalkPipeBrowser:
    """Interactive terminal browser for TalkPipe documentation."""

    def __init__(self):
        self.components: Dict[str, TalkPipeDoc] = {}  # Maps primary name to component
        self.name_to_primary: Dict[str, str] = {}  # Maps any name to primary name
        self.modules: Dict[str, List[str]] = {}
        self.load_components()
    
    def _extract_parameters(self, cls: type) -> Dict[str, str]:
        """Extract parameter information from a class or function."""
        return extract_parameters_dict(cls)
    
    def load_components(self):
        """Load all components from the plugin system, grouping multiple names for the same class."""
        load_plugins()  # Ensure plugins are loaded

        # Group components by class to consolidate multiple names
        class_to_names = {}
        class_to_type = {}

        # Load sources
        for chatterlang_name, cls in input_registry.all.items():
            if cls not in class_to_names:
                class_to_names[cls] = []
                class_to_type[cls] = "Source"
            class_to_names[cls].append(chatterlang_name)

        # Load segments
        for chatterlang_name, cls in segment_registry.all.items():
            if cls not in class_to_names:
                class_to_names[cls] = []
                class_to_type[cls] = detect_component_type(cls, "Segment")
            class_to_names[cls].append(chatterlang_name)

        # Create consolidated components
        for cls, names in class_to_names.items():
            # Sort names to ensure consistent primary name selection
            names.sort()
            primary_name = names[0]

            component_info = extract_component_info(primary_name, cls, class_to_type[cls])
            if component_info:
                self._load_component_from_info(component_info, names)
    
    def _load_component_from_info(self, component_info, all_names: List[str]):
        """Load a single component from ComponentInfo into the browser."""
        try:
            # Convert parameters from ParamSpec list to dict for browser compatibility
            parameters = {}
            
            # First pass: calculate max widths for alignment
            max_name_width = 0
            max_type_width = 0
            max_default_width = 0

            def _one_line(text) -> str:
                """Convert any text to a single-line string for aligned display.
                Collapses all whitespace (including newlines) to single spaces."""
                if text is None:
                    return ""
                s = str(text)
                # Collapse all whitespace (spaces, tabs, newlines) into single spaces
                return " ".join(s.split())
            
            for param in component_info.parameters:
                max_name_width = max(max_name_width, len(param.name))
                if param.annotation:
                    max_type_width = max(max_type_width, len(_one_line(param.annotation)))
                if param.default:
                    max_default_width = max(max_default_width, len(_one_line(param.default)))
            
            # Cap default padding so excessively long defaults don't push comments far right
            DEFAULT_PAD_CAP = 10
            default_pad_width = min(max_default_width, DEFAULT_PAD_CAP)

            # Second pass: format with proper alignment
            for param in component_info.parameters:
                param_str = param.name.ljust(max_name_width)
                
                if param.annotation:
                    ann = _one_line(param.annotation)
                    param_str += f": {ann.ljust(max_type_width)}"
                elif max_type_width > 0:  # Add spacing even if no type for this param
                    param_str += f"  {' ' * max_type_width}"
                
                # Align comments: pad defaults up to a capped width; if no default, pad spaces
                if default_pad_width > 0:
                    if param.default:
                        default_str = _one_line(param.default)
                        if len(default_str) <= default_pad_width:
                            # Pad default to capped width
                            param_str += f" = {default_str.ljust(default_pad_width)}"
                        else:
                            # Too long; print without padding so comment follows immediately
                            param_str += f" = {default_str}"
                    else:
                        # No default; pad the space where ' = <default>' would be
                        param_str += " " * (3 + default_pad_width)
                
                if param.description:
                    param_str += f"  // {param.description}"
                
                parameters[param.name] = param_str
            
            # Create component
            component = TalkPipeDoc(
                name=component_info.name,
                chatterlang_names=all_names,
                doc_type=component_info.component_type,
                module=component_info.module,
                base_classes=component_info.base_classes,
                docstring=component_info.docstring,
                parameters=parameters
            )

            # Store component under primary name
            primary_name = all_names[0]
            self.components[primary_name] = component

            # Map all names to the primary name for lookup
            for name in all_names:
                self.name_to_primary[name] = primary_name
            
            # Group by module
            if component_info.module not in self.modules:
                self.modules[component_info.module] = []
            self.modules[component_info.module].append(primary_name)
            
        except Exception as e:
            print(f"Warning: Failed to load component {component_info.chatterlang_name}: {e}")
    
    def run(self):
        """Run the interactive browser."""
        print("🔧 TalkPipe Documentation Browser")
        print("=" * 50)
        print("Commands:")
        print("  list                - List all modules")
        print("  list <module>       - List components in module")
        print("  show <component>    - Show detailed component info")
        print("  search <term>       - Search components and descriptions")
        print("  help                - Show this help")
        print("  quit                - Exit browser")
        print()
        
        while True:
            try:
                command = input("talkpipe> ").strip()
                if not command:
                    continue
                
                parts = command.split(' ', 1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                
                if cmd == 'quit' or cmd == 'exit':
                    break
                elif cmd == 'help':
                    self._show_help()
                elif cmd == 'list':
                    if arg:
                        self._list_module_components(arg)
                    else:
                        self._list_modules()
                elif cmd == 'show':
                    if arg:
                        self._show_component(arg)
                    else:
                        print("Usage: show <component_name>")
                elif cmd == 'search':
                    if arg:
                        self._search_components(arg)
                    else:
                        print("Usage: search <search_term>")
                else:
                    print(f"Unknown command: {cmd}. Type 'help' for available commands.")
            
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except EOFError:
                break
    
    def _show_help(self):
        """Show help information."""
        print("\nTalkPipe Documentation Browser Help")
        print("-" * 35)
        print("list                 - Show all available modules")
        print("list <module>        - Show components in a specific module")
        print("show <component>     - Show detailed info about a component")
        print("search <term>        - Search for components by name or description")
        print("help                 - Show this help message")
        print("quit/exit            - Exit the browser")
        print("\nExamples:")
        print("  list talkpipe.data.email")
        print("  show readEmail")
        print("  search mongodb")
        print()
    
    def _list_modules(self):
        """List all available modules."""
        print(f"\nAvailable Modules ({len(self.modules)}):")
        print("-" * 30)
        for module, components in sorted(self.modules.items()):
            print(f"📦 {module:<35} ({len(components)} components)")
        print()
    
    def _list_module_components(self, module_name: str):
        """List components in a specific module."""
        # Try exact match first
        if module_name not in self.modules:
            # Try partial match
            matches = [mod for mod in self.modules.keys() if module_name in mod]
            if len(matches) == 1:
                module_name = matches[0]
            elif len(matches) > 1:
                print(f"Multiple modules found matching '{module_name}':")
                for match in matches:
                    print(f"  {match}")
                return
            else:
                print(f"Module '{module_name}' not found.")
                print("Available modules:", ", ".join(sorted(self.modules.keys())))
                return
        
        components = self.modules[module_name]
        print(f"\nComponents in {module_name} ({len(components)}):")
        print("-" * 50)
        
        for comp_name in sorted(components):
            comp = self.components[comp_name]
            if comp.doc_type == "Source":
                type_icon = "🔌"
            elif comp.doc_type == "Field Segment":
                type_icon = "🔧"
            else:
                type_icon = "⚙️"
            print(f"{type_icon} {comp.all_names_display:<30} ({comp.name})")
        print()
    
    def _show_component(self, component_name: str):
        """Show detailed information about a component."""
        # Try exact match using name lookup
        primary_name = self.name_to_primary.get(component_name)
        component = None

        if primary_name:
            component = self.components.get(primary_name)

        # If not found, try case-insensitive search in all names
        if not component:
            matches = [name for name in self.name_to_primary.keys()
                      if name.lower() == component_name.lower()]
            if matches:
                primary_name = self.name_to_primary[matches[0]]
                component = self.components[primary_name]
        
        # If still not found, suggest similar names
        if not component:
            similar = [name for name in self.name_to_primary.keys()
                      if component_name.lower() in name.lower()]
            if similar:
                print(f"Component '{component_name}' not found. Did you mean:")
                for name in similar[:5]:
                    print(f"  {name}")
            else:
                print(f"Component '{component_name}' not found.")
            return
        
        # Display component details
        print(f"\n{'='*60}")
        print(f"📋 {component.all_names_display}")
        print(f"{'='*60}")
        print(f"Class/Function: {component.name}")
        print(f"Type:           {component.doc_type}")
        print(f"Module:         {component.module}")
        
        if component.base_classes:
            print(f"Base Classes:   {', '.join(component.base_classes)}")
        
        if component.docstring:
            print(f"\nDescription:")
            print("-" * 12)
            # Format docstring with proper indentation
            lines = component.docstring.split('\n')
            for line in lines:
                print(f"  {line}")
        
        if component.parameters:
            print(f"\nParameters:")
            print("-" * 11)
            for param_name, param_info in component.parameters.items():
                print(f"  {param_info}")
        
        print()
    
    def _search_components(self, search_term: str):
        """Search for components by name or description."""
        search_lower = search_term.lower()
        matches = []

        for comp_name, component in self.components.items():
            # Search in all chatterlang names, class name, and docstring
            name_match = any(search_lower in name.lower() for name in component.chatterlang_names)
            if (name_match or
                search_lower in component.name.lower() or
                search_lower in component.docstring.lower()):
                matches.append(component)
        
        if not matches:
            print(f"No components found matching '{search_term}'")
            return
        
        print(f"\nSearch Results for '{search_term}' ({len(matches)} found):")
        print("-" * 60)
        
        for component in sorted(matches, key=lambda x: x.primary_name):
            if component.doc_type == "Source":
                type_icon = "🔌"
            elif component.doc_type == "Field Segment":
                type_icon = "🔧"
            else:
                type_icon = "⚙️"
            print(f"{type_icon} {component.all_names_display:<30} ({component.module})")
            
            # Show brief description
            if component.docstring:
                first_line = component.docstring.split('\n')[0]
                if len(first_line) > 60:
                    first_line = first_line[:57] + "..."
                print(f"   {first_line}")
            print()


def main():
    
    try:
        browser = TalkPipeBrowser()
        if not browser.components:
            print("No TalkPipe components found. Make sure plugins are properly installed.")
            sys.exit(1)
        
        print(f"Loaded {len(browser.components)} components from {len(browser.modules)} modules")
        browser.run()
    except Exception as e:
        print(f"Error initializing browser: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()