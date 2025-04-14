import os
import ast
import sys
import html  # <-- Fix: Import the html module for html.escape
from typing import Optional, List
from dataclasses import dataclass, field

# Python 3.9+ can unparse AST natively. We'll check if it's available:
AST_UNPARSE_AVAILABLE = (sys.version_info.major > 3) or (
    sys.version_info.major == 3 and sys.version_info.minor >= 9
)

def safe_unparse(node: ast.AST) -> str:
    """
    Safely unparse an AST node if running on Python 3.9+.
    Otherwise, return a placeholder or implement a fallback.
    """
    if not node:
        return ""
    if AST_UNPARSE_AVAILABLE:
        import ast
        return ast.unparse(node)
    else:
        return "<unparse not supported in this Python version>"

@dataclass
class ParamSpec:
    """
    Holds detailed parameter info: name, annotation, default.
    """
    name: str
    annotation: str = ""
    default: str = ""

@dataclass
class AnalyzedItem:
    """
    Represents a discovered class or function along with its metadata.
    """
    type: str                 # "Class" or "Function"
    name: str
    docstring: str            # raw docstring (may contain HTML)
    parameters: List[ParamSpec]
    package_name: str = ""    # dotted module path
    chatterlang_name: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    
    # For classes: 'segment', 'source', or 'field_segment'
    # For functions: booleans is_segment, is_source, is_field_segment
    decorator_type: Optional[str] = None
    is_segment: bool = False
    is_source: bool = False
    is_field_segment: bool = False  # New field for field_segment

def _extract_chatterlang_name(decorator: ast.Call) -> Optional[str]:
    """
    Extract a string passed to @register_segment(...) or @register_source(...),
    either as the first positional argument or via name="..." keyword.
    """
    if decorator.args and isinstance(decorator.args[0], ast.Str):
        return decorator.args[0].s
    for kw in decorator.keywords or []:
        if kw.arg == 'name' and isinstance(kw.value, ast.Str):
            return kw.value.s
    return None

def build_param_specs(args_list: List[ast.arg], defaults_list: List[ast.expr]) -> List[ParamSpec]:
    """
    Build a list of ParamSpec from a function's args and defaults AST lists.
    - 'args_list': the full list of arguments (including 'self' if present).
    - 'defaults_list': the default values for the *last* len(defaults_list) arguments.
    """
    param_specs = []
    num_no_defaults = len(args_list) - len(defaults_list)
    for i, arg_node in enumerate(args_list):
        name = arg_node.arg
        annotation_str = safe_unparse(arg_node.annotation) if arg_node.annotation else ""
        if i >= num_no_defaults:
            # This arg has a default value
            default_index = i - num_no_defaults
            default_expr = defaults_list[default_index]
            default_str = safe_unparse(default_expr)
        else:
            default_str = ""
        param_specs.append(ParamSpec(name=name, annotation=annotation_str, default=default_str))
    return param_specs

def sanitize_id(text: str) -> str:
    """
    Convert arbitrary text into a safe HTML id by replacing characters
    likely to cause issues (like '.' or '/') with dashes.
    """
    return text.replace('.', '-').replace('/', '-').replace(' ', '-')

def analyze_function(node: ast.FunctionDef, filename: str, package_name: str) -> Optional[AnalyzedItem]:
    """
    Analyze a function node, looking for:
      - @register_segment(...) / @register_source(...)
      - @segment / @source / @field_segment
      - or attribute-based forms (e.g. @registry.register_segment(...))
    """
    is_segment = False
    is_source = False
    is_field_segment = False  # New flag
    chatterlang_name = None
    docstring = ast.get_docstring(node) or ""

    params = build_param_specs(node.args.args, node.args.defaults)

    # Check decorators
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            # e.g. @register_segment("foo")
            if isinstance(func, ast.Name):
                if func.id == 'register_segment':
                    is_segment = True
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.id == 'register_source':
                    is_source = True
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.id == 'segment':
                    is_segment = True
                elif func.id == 'source':
                    is_source = True
                elif func.id == 'field_segment':  # New: detect field_segment
                    is_field_segment = True
            elif isinstance(func, ast.Attribute):
                # e.g. @registry.register_segment("foo")
                if func.attr == 'register_segment':
                    is_segment = True
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.attr == 'register_source':
                    is_source = True
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
        elif isinstance(decorator, ast.Name):
            # e.g. @segment or @source or @field_segment
            if decorator.id == 'segment':
                is_segment = True
            elif decorator.id == 'source':
                is_source = True
            elif decorator.id == 'field_segment':  # New: detect field_segment
                is_field_segment = True

    # If no relevant decorators, ignore
    if not (is_segment or is_source or is_field_segment):
        return None

    return AnalyzedItem(
        type="Function",
        name=node.name,
        docstring=docstring,  # raw
        parameters=params,
        package_name=package_name,
        chatterlang_name=chatterlang_name,
        base_classes=[],
        decorator_type=None,  # classes only
        is_segment=is_segment,
        is_source=is_source,
        is_field_segment=is_field_segment,  # New field
    )

def analyze_class(node: ast.ClassDef, filename: str, package_name: str) -> Optional[AnalyzedItem]:
    """
    Analyze a class node, looking for @register_segment(...), @register_source(...),
    or field_segment-related decorators.
    """
    chatterlang_name = None
    decorator_type = None

    # Check the class decorators
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name):
                if func.id == 'register_segment':
                    decorator_type = 'segment'
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.id == 'register_source':
                    decorator_type = 'source'
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.id == 'register_field_segment':  # New: detect register_field_segment
                    decorator_type = 'field_segment'
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
            elif isinstance(func, ast.Attribute):
                if func.attr == 'register_segment':
                    decorator_type = 'segment'
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.attr == 'register_source':
                    decorator_type = 'source'
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted
                elif func.attr == 'register_field_segment':  # New: detect register_field_segment
                    decorator_type = 'field_segment'
                    extracted = _extract_chatterlang_name(decorator)
                    if extracted:
                        chatterlang_name = extracted

    if not decorator_type:
        # Not a segment, source, or field_segment class
        return None

    # Rest of the function remains the same...
    init_node = None
    for body_item in node.body:
        if isinstance(body_item, ast.FunctionDef) and body_item.name == "__init__":
            init_node = body_item
            break

    params: List[ParamSpec] = []
    if init_node:
        params = build_param_specs(init_node.args.args, init_node.args.defaults)

    docstring = ast.get_docstring(node) or ""

    base_classes: List[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            base_classes.append(base.id)
        elif isinstance(base, ast.Attribute):
            base_classes.append(f"{base.value.id}.{base.attr}")

    return AnalyzedItem(
        type="Class",
        name=node.name,
        docstring=docstring,
        parameters=params,
        package_name=package_name,
        chatterlang_name=chatterlang_name,
        base_classes=base_classes,
        decorator_type=decorator_type,
        is_segment=False,
        is_source=False,
        is_field_segment=False,
    )

# ------------------------------------------------------------------------
# FILE / AST PROCESSING
# ------------------------------------------------------------------------

def compute_package_name(file_path: str, root_dir: str) -> str:
    """
    Convert the file path (relative to root_dir) into a dotted module path.
    e.g. root_dir=/projects/myapp, file_path=/projects/myapp/mypkg/subpkg/module.py
    => package_name = mypkg.subpkg.module
    """
    rel_path = os.path.relpath(file_path, start=root_dir)
    rel_no_ext, _ = os.path.splitext(rel_path)
    return rel_no_ext.replace(os.path.sep, '.')

def find_python_files(root_dir: str) -> List[str]:
    """
    Recursively find all .py files under root_dir.
    """
    python_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".py"):
                full_path = os.path.join(dirpath, fname)
                python_files.append(full_path)
    return python_files

def analyze_file(file_path: str, root_dir: str) -> List[AnalyzedItem]:
    """
    Parse one Python file and analyze all top-level classes and functions.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        file_contents = f.read()

    tree = ast.parse(file_contents)
    items = []
    package_name = compute_package_name(file_path, root_dir)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            item = analyze_class(node, file_path, package_name)
            if item:
                items.append(item)
        elif isinstance(node, ast.FunctionDef):
            item = analyze_function(node, file_path, package_name)
            if item:
                items.append(item)

    return items

# ------------------------------------------------------------------------
# HTML GENERATION (WITH TABLE OF CONTENTS)
# ------------------------------------------------------------------------

def get_first_docstring_line(docstring: str) -> str:
    """
    Extract and return the first non-empty line from a docstring.
    """
    if not docstring:
        return ""
    lines = docstring.strip().splitlines()
    for line in lines:
        if line.strip():
            return line.strip()
    return ""

def generate_html(analyzed_items: List[AnalyzedItem], output_file: str) -> None:
    """
    Generate a styled HTML file with a table of contents, raw HTML docstrings,
    skipping 'self', and skipping first param for segment functions.
    """
    # Group by package, then sort packages
    items_by_package = {}
    for it in analyzed_items:
        items_by_package.setdefault(it.package_name, []).append(it)
    sorted_pkgs = sorted(items_by_package.keys())

    html_content = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Class and Function Documentation</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 0;
    }
    .container {
      max-width: 900px;
      margin: 0 auto;
      padding: 20px;
    }
    .toc {
      margin-bottom: 30px;
      padding: 10px;
      background-color: #f2f2f2;
      border: 1px solid #ccc;
    }
    .toc h2 {
      margin-top: 0;
    }
    .toc-table {
      width: 100%;
      border-collapse: collapse;
    }
    .toc-table th, .toc-table td {
      padding: 5px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid #ddd;
    }
    .toc-table th {
      font-weight: bold;
      background-color: #e5e5e5;
    }
    .toc-package {
      font-weight: bold;
      font-size: 1.2em;
      background-color: #f0f0f0;
      padding: 6px 3px;
    }
    .toc-name {
      width: 25%;
    }
    .toc-talkpipe {
      width: 25%;
      color: #0056b3;
      font-style: italic;
    }
    .toc-description {
      width: 50%;
    }
    .package-header {
      margin-top: 40px;
      margin-bottom: 10px;
      padding: 5px 0;
      border-bottom: 2px solid #aaa;
      font-size: 1.4em;
      font-weight: bold;
      color: #444;
    }
    .class, .function {
      margin: 20px 0;
      padding: 10px;
      border: 1px solid #ddd;
      background-color: #f9f9f9;
    }
    .function {
      background-color: #f9f9f9;
    }
    h2 {
      color: #333;
      margin-bottom: 5px;
    }
    .talkpipe-name {
      font-weight: bold;
      color: #007bff;
    }
    .param-list {
      margin: 5px 0;
      padding-left: 20px;
    }
    .param-list li {
      margin-bottom: 5px;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Class and Function Documentation</h1>
    <div class="toc">
      <h2>Table of Contents</h2>
      <table class="toc-table">
        <thead>
          <tr>
            <th class="toc-name">Name</th>
            <th class="toc-talkpipe">Chatterlang Name</th>
            <th class="toc-description">Description</th>
          </tr>
        </thead>
        <tbody>
"""

    # Build the table of contents with table structure
    for pkg in sorted_pkgs:
        pkg_items = items_by_package[pkg]
        pkg_items.sort(key=lambda x: x.name.lower())
        pkg_id = sanitize_id(pkg)

        # Package header row
        html_content += f'<tr><td class="toc-package" colspan="3"><a href="#{pkg_id}">{html.escape(pkg)}</a></td></tr>\n'

        # Each item under this package
        for item in pkg_items:
            item_id = f"{pkg_id}-{sanitize_id(item.name)}"
            first_doc_line = get_first_docstring_line(item.docstring)
            
            # Name column
            html_content += f'<tr>\n'
            html_content += f'  <td class="toc-name"><a href="#{item_id}">{html.escape(item.name)}</a></td>\n'
            
            # Talkpipe column
            html_content += f'  <td class="toc-talkpipe">'
            if item.chatterlang_name:
                html_content += f'{html.escape(item.chatterlang_name)}'
            html_content += '</td>\n'
            
            # Description column
            html_content += f'  <td class="toc-description">'
            if first_doc_line:
                html_content += f'{html.escape(first_doc_line)}'
            html_content += '</td>\n'
            
            html_content += '</tr>\n'

    html_content += """\
        </tbody>
      </table>
    </div>
"""

    # Now the main content, grouped by package
    for pkg in sorted_pkgs:
        pkg_items = items_by_package[pkg]
        pkg_items.sort(key=lambda x: x.name.lower())

        pkg_id = sanitize_id(pkg)
        html_content += f'<div class="package-header" id="{pkg_id}">{html.escape(pkg)}</div>\n'

        for item in pkg_items:
            if item.type == "Class":
                if item.decorator_type == 'segment':
                    disp_type = "Segment Class"
                elif item.decorator_type == 'source':
                    disp_type = "Source Class"
                elif item.decorator_type == 'field_segment':  # New display type
                    disp_type = "Field Segment Class"
                else:
                    disp_type = "Class"
            else:
                if item.is_segment:
                    disp_type = "Segment Function"
                elif item.is_source:
                    disp_type = "Source Function"
                elif item.is_field_segment:  # New display type
                    disp_type = "Field Segment Function"
                else:
                    disp_type = "Function"

            item_id = f"{pkg_id}-{sanitize_id(item.name)}"
            html_content += f'<div class="{item.type.lower()}" id="{item_id}">\n'
            html_content += f'  <h2>{disp_type}: {item.name}</h2>\n'

            if item.chatterlang_name:
                html_content += f'  <p class="talkpipe-name">Chatterlang Name: {item.chatterlang_name}</p>\n'

            if item.docstring.strip():
                # Insert raw docstring (may contain HTML)
                html_content += f'  <div><pre>{item.docstring}</pre></div>\n'

            # Process parameters
            filtered_params = [p for p in item.parameters if p.name != "self" and p.name != "items" or p.name != "item"]
            if item.type == "Function" and item.is_segment and len(filtered_params) > 0:
                filtered_params = filtered_params[1:]

            if filtered_params:
                html_content += '  <h3>Parameters:</h3>\n  <ul class="param-list">\n'
                for p in filtered_params:
                    line_parts = [p.name]
                    if p.annotation:
                        line_parts.append(f": {p.annotation}")
                    if p.default:
                        line_parts.append(f" = {p.default}")
                    param_line = "".join(line_parts)
                    # Use html.escape for param_line
                    html_content += f"    <li>{html.escape(param_line)}</li>\n"
                html_content += '  </ul>\n'

            if item.base_classes:
                bases_line = ", ".join(item.base_classes)
                html_content += f'  <p><strong>Base Classes:</strong> {bases_line}</p>\n'

            html_content += '</div>\n'

    html_content += """\
  </div>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

# ------------------------------------------------------------------------
# TEXT GENERATION
# ------------------------------------------------------------------------

def generate_text(analyzed_items: List[AnalyzedItem], output_file: str) -> None:
    """
    Write a nicely formatted plain-text version of the same documentation.
    Group by package, sorted, omit 'self', skip first param for segment functions.
    No table of contents here - just a linear, grouped listing.
    """
    items_by_package = {}
    for it in analyzed_items:
        items_by_package.setdefault(it.package_name, []).append(it)
    sorted_pkgs = sorted(items_by_package.keys())

    lines = []
    lines.append("Class and Function Documentation (Text Version)")
    lines.append("================================================")
    lines.append("")

    for pkg in sorted_pkgs:
        pkg_items = items_by_package[pkg]
        pkg_items.sort(key=lambda x: x.name.lower())

        lines.append(f"PACKAGE: {pkg}")
        lines.append("-" * (len("PACKAGE: ") + len(pkg)))  # underline
        lines.append("")

        for item in pkg_items:
            if item.type == "Class":
                if item.decorator_type == 'segment':
                    disp_type = "Segment Class"
                elif item.decorator_type == 'source':
                    disp_type = "Source Class"
                elif item.decorator_type == 'field_segment':  # New display type
                    disp_type = "Field Segment Class"
                else:
                    disp_type = "Class"
            else:
                if item.is_segment:
                    disp_type = "Segment Function"
                elif item.is_source:
                    disp_type = "Source Function"
                elif item.is_field_segment:  # New display type
                    disp_type = "Field Segment Function"
                else:
                    disp_type = "Function"

            lines.append(f"{disp_type}: {item.name}")
            if item.chatterlang_name:
                lines.append(f"  Chatterlang Name: {item.chatterlang_name}")

            if item.base_classes:
                lines.append(f"  Base Classes: {', '.join(item.base_classes)}")

            if item.docstring.strip():
                lines.append("  Docstring:")
                for ds_line in item.docstring.splitlines():
                    lines.append(f"    {ds_line}")
            else:
                lines.append("  Docstring: (none)")

            filtered_params = [p for p in item.parameters if p.name != "self"]
            if item.type == "Function" and item.is_segment and len(filtered_params) > 0:
                filtered_params = filtered_params[1:]

            if filtered_params:
                lines.append("  Parameters:")
                for p in filtered_params:
                    param_str = f"    {p.name}"
                    if p.annotation:
                        param_str += f": {p.annotation}"
                    if p.default:
                        param_str += f" = {p.default}"
                    lines.append(param_str)
            lines.append("")

        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

# ------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------

def main(root_dir: str, html_file: str, text_file: str) -> None:
    """
    We expect two output files: an HTML output (with a table of contents)
    and a text output (no table of contents).
    """
    py_files = find_python_files(root_dir)
    all_items = []
    for pf in py_files:
        all_items.extend(analyze_file(pf, root_dir))

    # Generate both files
    generate_html(all_items, html_file)
    generate_text(all_items, text_file)

    print(f"HTML documentation generated at {html_file}")
    print(f"Text documentation generated at {text_file}")

def go():
    if len(sys.argv) not in {1, 4}:
        print("Error: You must provide either 0 or 3 arguments.")
        print("Usage: python unit-documentation-analyzer.py [root_or_package html_out text_out]")
        sys.exit(1)
    elif len(sys.argv) == 1:
        print("No arguments provided. Using default arguments: talkpipe ./talkpipe_ref.html ./talkpipe_ref.txt")
        root_or_package = "talkpipe"
        html_out = "./talkpipe_ref.html"
        text_out = "./talkpipe_ref.txt"
    else:
        root_or_package = sys.argv[1]
        html_out = sys.argv[2]
        text_out = sys.argv[3]

    # Check if the input is a package name first
    try:
        import importlib.util
        spec = importlib.util.find_spec(root_or_package)
        if spec and spec.submodule_search_locations:
            root_dir = spec.submodule_search_locations[0]
        else:
            # If not a package, check if it's a directory
            if os.path.isdir(root_or_package):
                root_dir = root_or_package
            else:
                raise ImportError(f"Cannot find package or directory '{root_or_package}'")
    except ImportError as e:
        print(e)
        sys.exit(1)

    main(root_dir, html_out, text_out)

if __name__ == "__main__":
    go()