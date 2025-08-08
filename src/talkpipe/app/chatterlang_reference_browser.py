#!/usr/bin/env python3
"""
TalkPipe Documentation Browser

A terminal-based interactive browser for TalkPipe documentation.
Allows browsing packages, searching for components, and viewing detailed documentation.
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class TalkPipeDoc:
    """Represents a single TalkPipe component (class or function)."""
    
    def __init__(self, name: str, chatterlang_name: str, doc_type: str, 
                 package: str, base_classes: List[str], docstring: str, 
                 parameters: Dict[str, str]):
        self.name = name
        self.chatterlang_name = chatterlang_name
        self.doc_type = doc_type  # 'Source Class', 'Segment Class', 'Segment Function', etc.
        self.package = package
        self.base_classes = base_classes
        self.docstring = docstring
        self.parameters = parameters


class TalkPipeBrowser:
    """Interactive terminal browser for TalkPipe documentation."""
    
    def __init__(self, doc_path: str):
        self.doc_path = Path(doc_path)
        self.components: Dict[str, TalkPipeDoc] = {}
        self.packages: Dict[str, List[str]] = {}
        self.load_documentation()
    
    def load_documentation(self):
        """Parse the talkpipe_ref.txt or unit-docs.txt file and load all components."""
        # Try talkpipe_ref.txt first (current directory format)
        txt_file = self.doc_path / "talkpipe_ref.txt"
        if not txt_file.exists():
            # Try unit-docs.txt (installation directory format)
            txt_file = self.doc_path / "unit-docs.txt"
            if not txt_file.exists():
                print(f"Error: Could not find talkpipe_ref.txt or unit-docs.txt in {self.doc_path}")
                sys.exit(1)
        
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into packages
        package_sections = re.split(r'\n\nPACKAGE: ([^\n]+)\n-+\n', content)[1:]
        
        for i in range(0, len(package_sections), 2):
            package_name = package_sections[i]
            package_content = package_sections[i + 1]
            
            # Parse components in this package
            self._parse_package_components(package_name, package_content)
    
    def _parse_package_components(self, package_name: str, content: str):
        """Parse individual components within a package."""
        # Split by component headers - handle both with and without newlines before
        components = re.split(r'\n(?=(Source|Segment) (?:Class|Function): )', content)
        
        if package_name not in self.packages:
            self.packages[package_name] = []
        
        for component_text in components:
            if not component_text.strip():
                continue
            # Handle the case where the split includes the header
            if not component_text.startswith(('Source', 'Segment')) and '\n' in component_text:
                lines = component_text.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith(('Source', 'Segment')):
                        component_text = '\n'.join(lines[i:])
                        break
                else:
                    continue
            
            if component_text.startswith(('Source', 'Segment')):
                component = self._parse_component(package_name, component_text)
                if component:
                    self.components[component.chatterlang_name] = component
                    self.packages[package_name].append(component.chatterlang_name)
    
    def _parse_component(self, package_name: str, text: str) -> Optional[TalkPipeDoc]:
        """Parse a single component from its text representation."""
        lines = text.strip().split('\n')
        if not lines:
            return None
        
        # Parse header
        header_match = re.match(r'(Source|Segment) (Class|Function): (.+)', lines[0])
        if not header_match:
            return None
        
        doc_type = f"{header_match.group(1)} {header_match.group(2)}"
        name = header_match.group(3)
        
        chatterlang_name = ""
        base_classes = []
        docstring = ""
        parameters = {}
        
        # Parse the rest
        current_section = None
        docstring_lines = []
        param_lines = []
        
        for line in lines[1:]:
            line = line.strip()
            
            if line.startswith("Chatterlang Name: "):
                chatterlang_name = line.replace("Chatterlang Name: ", "")
            elif line.startswith("Base Classes: "):
                base_classes = [cls.strip() for cls in line.replace("Base Classes: ", "").split(',')]
            elif line == "Docstring:":
                current_section = "docstring"
            elif line == "Parameters:":
                current_section = "parameters"
            elif current_section == "docstring" and line:
                docstring_lines.append(line)
            elif current_section == "parameters" and line:
                param_lines.append(line)
        
        docstring = '\n'.join(docstring_lines).strip()
        
        # Parse parameters
        for param_line in param_lines:
            if ':' in param_line and '=' in param_line:
                param_name = param_line.split(':')[0].strip()
                param_value = param_line.split('=', 1)[1].strip()
                parameters[param_name] = param_value
            elif param_line.strip():
                parameters[param_line.strip()] = ""
        
        return TalkPipeDoc(name, chatterlang_name, doc_type, package_name, 
                          base_classes, docstring, parameters)
    
    def run(self):
        """Run the interactive browser."""
        print("🔧 TalkPipe Documentation Browser")
        print("=" * 50)
        print("Commands:")
        print("  list                - List all packages")
        print("  list <package>      - List components in package")
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
                        self._list_package_components(arg)
                    else:
                        self._list_packages()
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
        print("list                 - Show all available packages")
        print("list <package>       - Show components in a specific package")
        print("show <component>     - Show detailed info about a component")
        print("search <term>        - Search for components by name or description")
        print("help                 - Show this help message")
        print("quit/exit            - Exit the browser")
        print("\nExamples:")
        print("  list data.email")
        print("  show readEmail")
        print("  search mongodb")
        print()
    
    def _list_packages(self):
        """List all available packages."""
        print(f"\nAvailable Packages ({len(self.packages)}):")
        print("-" * 30)
        for package, components in sorted(self.packages.items()):
            print(f"📦 {package:<25} ({len(components)} components)")
        print()
    
    def _list_package_components(self, package_name: str):
        """List components in a specific package."""
        if package_name not in self.packages:
            print(f"Package '{package_name}' not found.")
            print("Available packages:", ", ".join(sorted(self.packages.keys())))
            return
        
        components = self.packages[package_name]
        print(f"\nComponents in {package_name} ({len(components)}):")
        print("-" * 50)
        
        for comp_name in sorted(components):
            comp = self.components[comp_name]
            type_icon = "🔌" if "Source" in comp.doc_type else "⚙️"
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
        print(f"Package:        {component.package}")
        
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
            for param_name, param_value in component.parameters.items():
                if param_value:
                    print(f"  {param_name:<20} = {param_value}")
                else:
                    print(f"  {param_name}")
        
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
            type_icon = "🔌" if "Source" in component.doc_type else "⚙️"
            print(f"{type_icon} {component.chatterlang_name:<20} ({component.package})")
            
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
    parser.add_argument("doc_path", nargs="?", help="Path to directory containing talkpipe_ref.txt (optional - uses current directory by default)")
    
    args = parser.parse_args()
    
    # If no path provided, check for reference files in current directory first
    if args.doc_path is None:
        current_dir = Path(os.getcwd())
        txt_file = current_dir / "talkpipe_ref.txt"
        
        # If reference files exist in current directory, use them directly
        if txt_file.exists():
            doc_path = str(current_dir)
        else:
            # Check installation directory for pre-installed documentation
            install_dir = Path(__file__).parent / 'static'
            install_txt_file = install_dir / "unit-docs.txt"
            
            if install_txt_file.exists():
                print("Using pre-installed documentation from installation directory.")
                doc_path = str(install_dir)
            else:
                # Files don't exist, try to run talkpipe_ref command to create them
                print("Reference files not found in current directory or installation directory.")
                print("Attempting to run 'chatterlang_reference_generator' command to generate them...")
                
                try:
                    import subprocess
                    subprocess.run(['chatterlang_reference_generator'], capture_output=True, text=True, check=True)
                    print("Successfully generated reference files.")
                    
                    # Check if files were created
                    if txt_file.exists():
                        doc_path = str(current_dir)
                    else:
                        print("Error: talkpipe_ref command completed but files were not created")
                        sys.exit(1)
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    print(f"Error running talkpipe_ref command: {e}")
                    print("Please either:")
                    print("  1. Install TalkPipe and ensure 'talkpipe_ref' is in PATH, or")
                    print("  2. Provide path to directory containing talkpipe_ref.txt")
                    sys.exit(1)
    else:
        if not os.path.exists(args.doc_path):
            print(f"Error: Directory {args.doc_path} does not exist")
            sys.exit(1)
        doc_path = args.doc_path
    
    browser = TalkPipeBrowser(doc_path)
    browser.run()


if __name__ == "__main__":
    main()