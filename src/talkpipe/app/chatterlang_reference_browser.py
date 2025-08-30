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
    
    def __init__(self, name: str, chatterlang_name: str, doc_type: str, 
                 module: str, base_classes: List[str], docstring: str, 
                 parameters: Dict[str, str]):
        self.name = name
        self.chatterlang_name = chatterlang_name
        self.doc_type = doc_type  # 'Source', 'Segment', 'Field Segment'
        self.module = module
        self.base_classes = base_classes
        self.docstring = docstring
        self.parameters = parameters


class TalkPipeBrowser:
    """Interactive terminal browser for TalkPipe documentation."""
    
    def __init__(self):
        self.components: Dict[str, TalkPipeDoc] = {}
        self.modules: Dict[str, List[str]] = {}
        self.load_components()
    
    def _extract_parameters(self, cls: type) -> Dict[str, str]:
        """Extract parameter information from a class or function."""
        return extract_parameters_dict(cls)
    
    def load_components(self):
        """Load all components from the plugin system."""
        load_plugins()  # Ensure plugins are loaded
        
        # Load sources
        for chatterlang_name, cls in input_registry.all.items():
            component_info = extract_component_info(chatterlang_name, cls, "Source")
            if component_info:
                self._load_component_from_info(component_info)
        
        # Load segments
        for chatterlang_name, cls in segment_registry.all.items():
            component_type = detect_component_type(cls, "Segment")
            component_info = extract_component_info(chatterlang_name, cls, component_type)
            if component_info:
                self._load_component_from_info(component_info)
    
    def _load_component_from_info(self, component_info):
        """Load a single component from ComponentInfo into the browser."""
        try:
            # Convert parameters from ParamSpec list to dict for browser compatibility
            parameters = {}
            for param in component_info.parameters:
                param_str = param.name
                if param.annotation:
                    param_str += f": {param.annotation}"
                if param.default:
                    param_str += f" = {param.default}"
                parameters[param.name] = param_str
            
            # Create component
            component = TalkPipeDoc(
                name=component_info.name,
                chatterlang_name=component_info.chatterlang_name,
                doc_type=component_info.component_type,
                module=component_info.module,
                base_classes=component_info.base_classes,
                docstring=component_info.docstring,
                parameters=parameters
            )
            
            self.components[component_info.chatterlang_name] = component
            
            # Group by module
            if component_info.module not in self.modules:
                self.modules[component_info.module] = []
            self.modules[component_info.module].append(component_info.chatterlang_name)
            
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
            print(f"{type_icon} {comp.chatterlang_name:<20} ({comp.name})")
        print()
    
    def _show_component(self, component_name: str):
        """Show detailed information about a component."""
        # Try exact match first
        component = self.components.get(component_name)
        
        # If not found, try case-insensitive search
        if not component:
            matches = [name for name in self.components.keys() 
                      if name.lower() == component_name.lower()]
            if matches:
                component = self.components[matches[0]]
        
        # If still not found, suggest similar names
        if not component:
            similar = [name for name in self.components.keys() 
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
        print(f"📋 {component.chatterlang_name}")
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
            # Search in chatterlang name, class name, and docstring
            if (search_lower in comp_name.lower() or 
                search_lower in component.name.lower() or 
                search_lower in component.docstring.lower()):
                matches.append(component)
        
        if not matches:
            print(f"No components found matching '{search_term}'")
            return
        
        print(f"\nSearch Results for '{search_term}' ({len(matches)} found):")
        print("-" * 60)
        
        for component in sorted(matches, key=lambda x: x.chatterlang_name):
            if component.doc_type == "Source":
                type_icon = "🔌"
            elif component.doc_type == "Field Segment":
                type_icon = "🔧"
            else:
                type_icon = "⚙️"
            print(f"{type_icon} {component.chatterlang_name:<20} ({component.module})")
            
            # Show brief description
            if component.docstring:
                first_line = component.docstring.split('\n')[0]
                if len(first_line) > 60:
                    first_line = first_line[:57] + "..."
                print(f"   {first_line}")
            print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Interactive TalkPipe documentation browser")
    parser.add_argument("--legacy", action="store_true", 
                       help="Use legacy file-based mode instead of live introspection")
    
    args = parser.parse_args()
    
    if args.legacy:
        print("Legacy file-based mode is no longer supported.")
        print("The browser now uses live plugin introspection for up-to-date information.")
        sys.exit(1)
    
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