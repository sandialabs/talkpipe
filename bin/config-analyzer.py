import os
import ast
import argparse

def extract_config_keys_from_file(file_path):
    """ Extracts configuration keys accessed via get_config() from a given Python file. """
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except SyntaxError:
            return {}

    config_keys = set()
    config_variables = set()  # To track config = get_config() assignments
    constant_assignments = {}  # To track constant assignments
    imported_names = {}  # To track imported names and their values

    class ConfigVisitor(ast.NodeVisitor):
        def visit_ImportFrom(self, node):
            """Tracks imports from other modules."""
            module = node.module
            for name in node.names:
                imported_name = name.asname if name.asname else name.name
                imported_names[imported_name] = {"module": module, "name": name.name}
            self.generic_visit(node)

        def visit_BoolOp(self, node):
            """Handles boolean operations like 'x or y'"""
            if isinstance(node.op, ast.Or):
                for value in node.values:
                    self.visit(value)
            self.generic_visit(node)

        def visit_Assign(self, node):
            """ Detects assignments like 'config = get_config()' or 'CONSTANT = "value"'. """
            # Handle assignments with boolean operations
            if isinstance(node.value, ast.BoolOp):
                self.visit_BoolOp(node.value)
            
            # Track get_config assignments
            if isinstance(node.value, ast.Call) and self.is_get_config_call(node.value):
                if isinstance(node.targets[0], ast.Name):
                    config_variables.add(node.targets[0].id)
            
            # Track constant assignments
            if isinstance(node.targets[0], ast.Name):
                if isinstance(node.value, ast.Constant):
                    constant_assignments[node.targets[0].id] = node.value.value
                # Track assignments of imported names
                elif isinstance(node.value, ast.Name) and node.value.id in imported_names:
                    constant_assignments[node.targets[0].id] = imported_names[node.value.id]

            self.generic_visit(node)

        def visit_Subscript(self, node):
            """ Detects dictionary-style access: config["key"]. """
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in config_variables  # Ensure it's from get_config()
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                config_keys.add(node.slice.value)
            self.generic_visit(node)

        def visit_Call(self, node):
            """ Detects method calls like config.get("key"), util.get_config().get("key"), and cfg.get(IMPORTED_CONSTANT). """
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and len(node.args) >= 1
            ):
                # Check if the call is on a config-like object
                if (isinstance(node.func.value, ast.Name) and 
                    (node.func.value.id in config_variables or 
                     node.func.value.id.lower().endswith('cfg'))):  # Added check for cfg-like names
                    
                    key_node = node.args[0]
                    self.handle_get_argument(key_node)

                # Case: util.get_config().get("key") or util.get_config().get("key", None)
                if self.is_get_config_call(node.func.value):
                    key_node = node.args[0]
                    self.handle_get_argument(key_node)

            self.generic_visit(node)

        def handle_get_argument(self, key_node):
            """Helper method to handle different types of arguments to .get() calls"""
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                config_keys.add(key_node.value)
            elif isinstance(key_node, ast.Name):
                # Handle case where the key is a constant variable
                if key_node.id in constant_assignments:
                    const_value = constant_assignments[key_node.id]
                    if isinstance(const_value, str):
                        config_keys.add(const_value)
                    elif isinstance(const_value, dict):
                        # This is an imported name - add it to config keys with a note
                        imported_info = f"IMPORTED: {const_value['module']}.{const_value['name']}"
                        config_keys.add(imported_info)
                elif key_node.id in imported_names:
                    # Direct use of imported name without reassignment
                    imported_info = f"IMPORTED: {imported_names[key_node.id]['module']}.{imported_names[key_node.id]['name']}"
                    config_keys.add(imported_info)

        def is_get_config_call(self, node):
            """ Checks if a function call is get_config() or util.get_config(). """
            return (
                (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_config")
                or
                (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get_config")
            )

    visitor = ConfigVisitor()
    visitor.visit(tree)

    return config_keys

def scan_directory_for_config_usage(directory):
    """ Scans all Python files in a directory for get_config key usage. """
    all_configs = {}

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                config_keys = extract_config_keys_from_file(file_path)
                if config_keys:
                    all_configs[file_path] = config_keys

    return all_configs

def main():
    parser = argparse.ArgumentParser(description="Scan a directory for get_config key usage in Python files.")
    parser.add_argument("directory", help="Path to the directory to scan.")

    args = parser.parse_args()
    directory = args.directory

    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        exit(1)

    config_usage = scan_directory_for_config_usage(directory)

    keys = sorted(list(set([key for keys in config_usage.values() for key in keys])))
    for key in keys:
        print(f"* **{key}** - ")
    

    for file, keys in config_usage.items():
        print(f"\nFile: {file}")
        for key in keys:
            print(f"  - Config Key: '{key}'")

if __name__ == "__main__":
    main()