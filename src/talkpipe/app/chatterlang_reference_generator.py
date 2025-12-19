import sys
import html
from typing import Optional, List
from dataclasses import dataclass, field
from talkpipe.chatterlang.registry import input_registry, segment_registry
from talkpipe.util.plugin_loader import load_plugins
from talkpipe.util.doc_extraction import (
    ParamSpec, ComponentInfo, extract_component_info, detect_component_type
)

# ParamSpec is now imported from doc_extraction

@dataclass
class AnalyzedItem:
    """
    Represents a discovered class or function along with its metadata.
    """
    type: str                 # "Source" or "Segment"
    name: str
    docstring: str            # raw docstring
    parameters: List[ParamSpec]
    chatterlang_name: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    
    # For segments: 'segment', 'source', or 'field_segment'
    decorator_type: Optional[str] = None
    is_segment: bool = False
    is_source: bool = False
    is_field_segment: bool = False

def sanitize_id(text: str) -> str:
    """
    Convert arbitrary text into a safe HTML id by replacing characters
    likely to cause issues (like '.' or '/') with dashes.
    """
    return text.replace('.', '-').replace('/', '-').replace(' ', '-')

def analyze_registered_items() -> List[AnalyzedItem]:
    """
    Analyze all registered sources and segments from the plugin system.
    Groups items with multiple chatterlang names together.
    """
    load_plugins()  # Ensure plugins are loaded

    # Group by class to handle multiple names for the same class
    class_to_names = {}

    # Process sources
    for chatterlang_name, cls in input_registry.all.items():
        if cls not in class_to_names:
            class_to_names[cls] = {'names': [], 'type': 'Source'}
        class_to_names[cls]['names'].append(chatterlang_name)

    # Process segments
    for chatterlang_name, cls in segment_registry.all.items():
        if cls not in class_to_names:
            component_type = detect_component_type(cls, 'Segment')
            class_to_names[cls] = {'names': [], 'type': component_type}
        class_to_names[cls]['names'].append(chatterlang_name)

    analyzed_items = []

    # Create AnalyzedItem objects with combined names
    for cls, info in class_to_names.items():
        # Sort names for consistent output
        sorted_names = sorted(info['names'])
        primary_name = sorted_names[0]  # Use first alphabetically as primary

        component_info = extract_component_info(primary_name, cls, info['type'])
        if component_info:
            item = convert_component_info_to_analyzed_item(component_info)
            # If multiple names, combine them
            if len(sorted_names) > 1:
                item.chatterlang_name = ', '.join(sorted_names)
            analyzed_items.append(item)

    return analyzed_items

def convert_component_info_to_analyzed_item(component_info: ComponentInfo) -> AnalyzedItem:
    """
    Convert ComponentInfo to AnalyzedItem for backward compatibility.
    """
    # Map component types to decorator types and flags
    decorator_type = None
    is_segment = False
    is_source = False
    is_field_segment = False
    
    if component_info.component_type == 'Source':
        is_source = True
        decorator_type = 'source'
        item_type = 'Source'
    elif component_info.component_type == 'Field Segment':
        is_field_segment = True
        decorator_type = 'field_segment'
        item_type = 'Segment'
    elif component_info.component_type == 'Segment':
        is_segment = True
        decorator_type = 'segment'
        item_type = 'Segment'
    else:
        item_type = component_info.component_type
    
    return AnalyzedItem(
        type=item_type,
        name=component_info.name,
        docstring=component_info.docstring,
        parameters=component_info.parameters,
        chatterlang_name=component_info.chatterlang_name,
        base_classes=component_info.base_classes,
        decorator_type=decorator_type,
        is_segment=is_segment,
        is_source=is_source,
        is_field_segment=is_field_segment,
    )

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
    # Group by type (Source/Segment), then sort by chatterlang name
    items_by_type = {}
    for item in analyzed_items:
        type_key = item.type
        items_by_type.setdefault(type_key, []).append(item)
    
    # Sort items within each type by chatterlang name
    for type_items in items_by_type.values():
        type_items.sort(key=lambda x: x.chatterlang_name.lower() if x.chatterlang_name else x.name.lower())

    html_content = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Chatterlang Reference Documentation</title>
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
    .toc-type {
      font-weight: bold;
      font-size: 1.2em;
      background-color: #f0f0f0;
      padding: 6px 3px;
    }
    .toc-name {
      width: 25%;
    }
    .toc-chatterlang {
      width: 25%;
      color: #0056b3;
      font-style: italic;
    }
    .toc-description {
      width: 50%;
    }
    .type-header {
      margin-top: 40px;
      margin-bottom: 10px;
      padding: 5px 0;
      border-bottom: 2px solid #aaa;
      font-size: 1.4em;
      font-weight: bold;
      color: #444;
    }
    .item {
      margin: 20px 0;
      padding: 10px;
      border: 1px solid #ddd;
      background-color: #f9f9f9;
    }
    h2 {
      color: #333;
      margin-bottom: 5px;
    }
    .chatterlang-name {
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
    <h1>Chatterlang Reference Documentation</h1>
    <div class="toc">
      <h2>Table of Contents</h2>
      <table class="toc-table">
        <thead>
          <tr>
            <th class="toc-chatterlang">Chatterlang Name</th>
            <th class="toc-name">Class Name</th>
            <th class="toc-description">Description</th>
          </tr>
        </thead>
        <tbody>
"""

    # Build the table of contents with table structure
    for item_type in sorted(items_by_type.keys()):
        type_items = items_by_type[item_type]
        type_id = sanitize_id(item_type)

        # Type header row
        html_content += f'<tr><td class="toc-type" colspan="3"><a href="#{type_id}">{html.escape(item_type)}</a></td></tr>\n'

        # Each item under this type
        for item in type_items:
            item_id = f"{type_id}-{sanitize_id(item.chatterlang_name or item.name)}"
            first_doc_line = get_first_docstring_line(item.docstring)
            
            # Chatterlang column (now first)
            html_content += f'<tr>\n'
            html_content += f'  <td class="toc-chatterlang">'
            if item.chatterlang_name:
                html_content += f'<a href="#{item_id}">{html.escape(item.chatterlang_name)}</a>'
            html_content += '</td>\n'
            
            # Name column (now second)
            html_content += f'  <td class="toc-name">{html.escape(item.name)}</td>\n'
            
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

    # Now the main content, grouped by type
    for item_type in sorted(items_by_type.keys()):
        type_items = items_by_type[item_type]
        type_id = sanitize_id(item_type)
        html_content += f'<div class="type-header" id="{type_id}">{html.escape(item_type)}</div>\n'

        for item in type_items:
            if item.decorator_type == 'segment':
                disp_type = "Segment"
            elif item.decorator_type == 'source':
                disp_type = "Source"
            elif item.decorator_type == 'field_segment':
                disp_type = "Field Segment"
            else:
                disp_type = item.type

            item_id = f"{type_id}-{sanitize_id(item.chatterlang_name or item.name)}"
            html_content += f'<div class="item" id="{item_id}">\n'
            html_content += f'  <h2>{disp_type}: {item.name}</h2>\n'

            if item.chatterlang_name:
                html_content += f'  <p class="chatterlang-name">Chatterlang Name: {item.chatterlang_name}</p>\n'

            if item.docstring.strip():
                # Insert raw docstring (may contain HTML)
                html_content += f'  <div><pre>{html.escape(item.docstring)}</pre></div>\n'

            # Process parameters - skip 'self' and for segments skip first param if it's the data param
            filtered_params = [p for p in item.parameters if p.name not in ["self", "items", "item"]]
            if item.is_segment and len(filtered_params) > 0:
                # For segments, the first param is often the data being processed
                filtered_params = filtered_params[1:] if len(filtered_params) > 1 else filtered_params

            if filtered_params:
                def _one_line(text) -> str:
                    if text is None:
                        return ""
                    s = str(text)
                    return " ".join(s.split())
                html_content += '  <h3>Parameters:</h3>\n  <ul class="param-list">\n'
                for p in filtered_params:
                    line_parts = [p.name]
                    if p.annotation:
                        line_parts.append(f": {_one_line(p.annotation)}")
                    if p.default:
                        line_parts.append(f" = {_one_line(p.default)}")
                    param_line = "".join(line_parts)
                    # Use html.escape for param_line
                    html_content += f"    <li>{html.escape(param_line)}</li>\n"
                html_content += '  </ul>\n'

            if item.base_classes:
                bases_line = ", ".join(item.base_classes)
                html_content += f'  <p><strong>Base Classes:</strong> {html.escape(bases_line)}</p>\n'

            html_content += '</div>\n'

    html_content += """\
  </div>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

def generate_text(analyzed_items: List[AnalyzedItem], output_file: str) -> None:
    """
    Write a nicely formatted plain-text version of the same documentation.
    Group by type, sorted, omit 'self', skip first param for segment functions.
    No table of contents here - just a linear, grouped listing.
    """
    # Group by type (Source/Segment), then sort by chatterlang name
    items_by_type = {}
    for item in analyzed_items:
        type_key = item.type
        items_by_type.setdefault(type_key, []).append(item)
    
    # Sort items within each type by chatterlang name
    for type_items in items_by_type.values():
        type_items.sort(key=lambda x: x.chatterlang_name.lower() if x.chatterlang_name else x.name.lower())

    lines = []
    lines.append("Chatterlang Reference Documentation (Text Version)")
    lines.append("==================================================")
    lines.append("")

    for item_type in sorted(items_by_type.keys()):
        type_items = items_by_type[item_type]

        lines.append(f"TYPE: {item_type}")
        lines.append("-" * (len("TYPE: ") + len(item_type)))  # underline
        lines.append("")

        for item in type_items:
            if item.decorator_type == 'segment':
                disp_type = "Segment"
            elif item.decorator_type == 'source':
                disp_type = "Source"
            elif item.decorator_type == 'field_segment':
                disp_type = "Field Segment"
            else:
                disp_type = item.type

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
            if item.is_segment and len(filtered_params) > 0:
                filtered_params = filtered_params[1:] if len(filtered_params) > 1 else filtered_params

            if filtered_params:
                def _one_line(text) -> str:
                    if text is None:
                        return ""
                    s = str(text)
                    return " ".join(s.split())
                lines.append("  Parameters:")
                for p in filtered_params:
                    param_str = f"    {p.name}"
                    if p.annotation:
                        param_str += f": {_one_line(p.annotation)}"
                    if p.default:
                        param_str += f" = {_one_line(p.default)}"
                    lines.append(param_str)
            lines.append("")

        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

def main(html_file: str, text_file: str) -> None:
    """
    Generate documentation using the plugin system registry.
    """
    analyzed_items = analyze_registered_items()
    
    # Generate both files
    generate_html(analyzed_items, html_file)
    generate_text(analyzed_items, text_file)

    print(f"HTML documentation generated at {html_file}")
    print(f"Text documentation generated at {text_file}")

def go():
    if len(sys.argv) not in {1, 3}:
        print("Error: You must provide either 0 or 2 arguments.")
        print("Usage: python chatterlang_reference_generator.py [html_out text_out]")
        sys.exit(1)
    elif len(sys.argv) == 1:
        print("No arguments provided. Using default arguments: ./chatterlang_ref.html ./chatterlang_ref.txt")
        html_out = "./chatterlang_ref.html"
        text_out = "./chatterlang_ref.txt"
    else:
        html_out = sys.argv[1]
        text_out = sys.argv[2]

    main(html_out, text_out)

if __name__ == "__main__":
    go()