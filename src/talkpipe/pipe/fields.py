"""Item-shaping segments: convert, extract, assign, format, and copy fields of each item."""

import copy
from collections.abc import Iterable, Iterator
from typing import Annotated, Any

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    AbstractSegment,
    field_segment,
    segment,
)
from talkpipe.util.config import parse_key_value_str
from talkpipe.util.data_manipulation import (
    assign_property,
    dict_to_text,
    extract_property,
    extract_template_field_names,
    fill_template,
    get_type_safely,
    toDict,
)


@registry.register_segment(name="cast")
class Cast(AbstractSegment[Any, Any]):
    """Casts the input data to a specified type.

    The type can be specified by passing a type object or a string representation of the type.
    The cast will optionally fail silently if the data cannot be cast to the specified type.
    This lets this segment also be used as a filter to remove data that cannot be cast.
    The cast occurs by calling the type object on the data.
    """

    def __init__(
        self,
        cast_type: Annotated[type | str, "The type to cast the data to."],
        fail_silently: Annotated[
            bool, "Whether to fail silently if the cast fails."
        ] = True,
    ):
        super().__init__()
        if isinstance(cast_type, type):
            self.cast_type = cast_type
        else:
            resolved = get_type_safely(cast_type)
            if resolved is None:
                known = [
                    "int",
                    "float",
                    "str",
                    "bool",
                    "bytes",
                    "list",
                    "tuple",
                    "dict",
                    "set",
                ]
                candidates = (
                    [k for k in known if k.startswith(cast_type[:2])]
                    if len(cast_type) >= 2
                    else known
                )
                hint = (
                    f"; did you mean '{candidates[0]}'?"
                    if candidates
                    else f"; valid built-in types include: {', '.join(known)}"
                )
                raise ValueError(f"Invalid cast_type '{cast_type}'{hint}")
            self.cast_type = resolved
        self.fail_silently = fail_silently

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Cast each item in the input stream to the specified type.

        Args:
            input_iter (Iterable): The input data
        """
        for data in input_iter:
            try:
                yield self.cast_type(data)
            except (ValueError, TypeError) as e:
                if not self.fail_silently:
                    raise ValueError(
                        f"Could not cast {data} to {self.cast_type}"
                    ) from e


@registry.register_segment(name="toDict")
class ToDict(AbstractSegment[Any, Any]):
    """Creates a dictionary from the input data."""

    def __init__(
        self,
        field_list: Annotated[
            str,
            "A list of properties in field_list format to extract from the input data.",
        ] = "_",
        fail_on_missing: Annotated[
            bool, "Whether to fail on missing properties."
        ] = True,
    ):
        """Convert each item in the input string into a dictionary based on the provided parameter list."""
        super().__init__()
        self.field_list = field_list
        self.fail_on_missing = fail_on_missing

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        for data in input_iter:
            ans = toDict(data, self.field_list, self.fail_on_missing)
            yield ans


@registry.register_segment("formatItem")
class FormattedItem(AbstractSegment[Any, Any]):
    """
    Generate formatted output for specified fields in "Property: Value" format.

    This segment takes each input item and generates one formatted string output
    containing all specified fields. Each field is in the format "Label: Value".

    Yields:
        str: One formatted string per input item containing all fields
    """

    def __init__(
        self,
        field_list: Annotated[str, "Comma-separated list of field:label pairs."] = "_",
        wrap_width: Annotated[int, "Width for text wrapping"] = 80,
        fail_on_missing: Annotated[
            bool, "Whether to fail if a field is missing"
        ] = False,
        field_name_separator: Annotated[
            str, "Separator between property and value"
        ] = ": ",
        field_separator: Annotated[str, "Separator between different fields"] = "\n",
        item_suffix: Annotated[str, "Suffix to append to each item"] = "",
    ):
        super().__init__()
        self.field_list = field_list
        self.wrap_width = wrap_width
        self.field_name_separator = field_name_separator
        self.fail_on_missing = fail_on_missing
        self.field_separator = field_separator
        self.item_suffix = item_suffix

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Transform each input item into a single formatted string"""
        for item in input_iter:
            d = toDict(item, self.field_list, self.fail_on_missing)
            # Use the standalone function to format the item
            formatted_string = dict_to_text(
                d,
                wrap_width=self.wrap_width,
                field_name_separator=self.field_name_separator,
                field_separator=self.field_separator,
                item_suffix=self.item_suffix,
            )

            # Yield one string per item
            yield formatted_string


@registry.register_segment("setAs")
@field_segment
def setAs(
    item: Any, field_list: Annotated[str, "Comma-separated list of field:label pairs."]
) -> Any:
    """Appends the specified fields to the input item.

    Equivalent to toDict except that the item is modified with the new key/value pairs
    rather than a new dictionary returned.

    Supports both dictionary-like objects and regular objects (including pydantic models).

    """
    new_vals = toDict(item, field_list)
    for k, v in new_vals.items():
        assign_property(item, k, v)
    return item


@registry.register_segment("extractProperty")
@field_segment
def extractProperty(
    item: Any, property: Annotated[str, "The property to extract from the input item."]
) -> Any:
    """Extracts the specified property from the input item.

    Returns:
        The value of the specified property.
    """
    return extract_property(item, property)


@registry.register_segment("set")
@segment()
def assign(
    items: Annotated[Iterable[Any], "The input item to modify"],
    value: Annotated[Any, "The value to assign"],
    set_as: Annotated[str, "The field to assign the value to"],
) -> Iterator[Any]:
    """Set a field to a constant value on each item in the pipeline.

    This segment modifies each input item by setting a specified field to the same
    value for every item. The modified items are then passed through for downstream
    processing.

    Useful for adding metadata, enriching items with constants, or setting default values.
    Works with dictionaries, objects, and Pydantic models.

    Yields:
        Modified items with the specified field set to the given value.
    """
    for item in items:
        assign_property(item, set_as, value)
        yield item


@registry.register_segment("concat")
@segment(fields=None, delimiter="\n\n", set_as=None)
def concat(
    items: Iterable[Any],
    fields: Annotated[str, "Comma-separated list of fields to concatenate."],
    delimiter: Annotated[str, "String to insert between concatenated fields."] = "\n\n",
    set_as: Annotated[
        str | None,
        "If specified, adds concatenated result as new field with this name.",
    ] = None,
) -> Iterator[Any]:
    """Concatenate specified fields from each item into a single string.

    This segment extracts multiple fields from each item, converts them to strings,
    and joins them with the specified delimiter. Can either replace the item with
    the concatenated string or add the result as a new field on the original item.

    Useful for combining text from multiple fields, creating composite keys, or
    generating summaries from item components.

    Yields:
        If set_as is specified: Original item with concatenated result added as new field.
        Otherwise: Just the concatenated string.
    """
    props = parse_key_value_str(fields)
    for item in items:
        ans = ""
        for i, prop in enumerate(props.items()):
            if i > 0:
                ans += delimiter
            ans += str(extract_property(item, prop[0]))
        if set_as:
            assign_property(item, set_as, ans)
            yield item
        else:
            yield ans


@registry.register_segment("slice")
@field_segment()
def slice(
    item: Any,
    range: Annotated[
        str | None,
        "String in format 'start:end' where both start and end are optional.",
    ] = None,
) -> Any:
    """Slices a sequence using start and end indices.

    This function takes a sequence and a range string in the format "start:end" to slice the sequence.
    Both start and end indices are optional.

    Args:
        item: Any sequence that supports slicing (e.g., list, string, tuple)
        range (str, optional): String in format "start:end" where both start and end are optional.
            For example: "2:5", ":3", "4:", ":" are all valid. Defaults to None.

    Returns:
        The sliced sequence containing elements from start to end index.
        If range is None, returns a full copy of the sequence.

    Examples:
        >>> slice([1, 2, 3, 4, 5], "1:3")
        [2, 3]
        >>> slice("hello", ":3")
        "hel"
        >>> slice([1, 2, 3, 4, 5], "2:")
        [3, 4, 5]
    """
    if range is None:
        start = None
        end = None
    else:
        sstring, send = range.split(":")
        start = int(sstring) if len(sstring) > 0 else None
        end = int(send) if len(send) > 0 else None

    return item[start:end]


@registry.register_segment("longestStr")
@segment()
def longestStr(
    items: Iterable[Any],
    field_list: Annotated[
        str, "Comma-separated list of fields to check for longest string."
    ],
    set_as: Annotated[
        str | None, "If specified, adds longest string as new field with this name."
    ] = None,
) -> Iterator[Any]:
    """Find the longest string value among specified fields in each item.

    Compares the string representations of multiple fields and returns the one
    with the greatest length. Non-string fields are converted to strings before
    comparison. Missing fields are ignored. If multiple fields have equal length,
    the first one is returned.

    Useful for selecting the most detailed description from multiple fields,
    or finding the fullest version of redundant data.

    Yields:
        The longest string found. If set_as is specified: original item with
        the longest string added as a new field. Otherwise: just the string.
    """
    fields = parse_key_value_str(field_list)
    for item in items:
        longest = ""
        for field in fields:
            data = extract_property(item, field, fail_on_missing=False)
            if data is None:
                continue
            if len(str(data)) > len(longest):
                longest = str(data)
        if set_as:
            assign_property(item, set_as, longest)
            yield item
        else:
            yield longest


@registry.register_segment("flatten")
@field_segment(multi_emit=True)
def flatten(item: Any) -> Iterator[Any]:
    """Flatten a nested collection by emitting its individual elements.

    For dictionaries: yields key-value tuples (like .items())
    For iterables: yields each element in the collection
    For non-iterables: yields the item unchanged

    Useful for expanding nested lists, unpacking collections, or flattening
    hierarchical data structures into individual items.

    Multi-emit segment: each input item can produce multiple output items.

    Yields:
        Individual elements from dictionaries, iterables, or the item itself.
    """
    if isinstance(item, dict):
        yield from item.items()
    else:
        try:
            yield from item
        except TypeError:
            yield item


@registry.register_segment("fillTemplate")
@field_segment
def fillTemplate(
    item: Any,
    template: Annotated[str, "The template string with placeholders for values"],
    fail_on_missing: Annotated[bool, "Whether to fail on missing fields"] = True,
    default: Annotated[Any | None, "Default value to use for missing fields"] = "",
) -> str:
    """Fill a template string with values from the input `item`.

        Template writing guide:
        - Placeholders: Use `{path}` where `path` is a dot-notation path
            resolved on `item` via `extract_property`. Examples: `{user.name}`,
            `{address.city}`, `{tags.0}` (numeric index for lists/tuples).
        - Whole item: `{_}` inserts the entire `item`. `_.field` acts as a
            passthrough, so `{_.name}` is equivalent to `{name}`.
        - Literal braces: Use `{{` and `}}` to render literal `{` and `}`
            characters in output.
        - Missing values: Controlled by `fail_on_missing` and `default`.
            If `fail_on_missing` is True, missing fields raise an error; otherwise,
            missing fields are replaced with `default` (empty string by default).

        Examples:
        - Dict item:
            item = {"user": {"name": "Alice"}, "day": "Monday"}
            template = "Hello {user.name}, today is {day}."
            -> "Hello Alice, today is Monday."

        - Lists and indices:
            item = {"tags": ["news", "tech"]}
            template = "First tag: {tags.0}"
            -> "First tag: news"

        - Literal braces:
            item = {"user": {"name": "Alice"}}
            template = "{{Escaped}} {_.user.name}"
            -> "{Escaped} Alice"

    Returns:
        str: The filled template string
    """
    if template is None:
        raise ValueError("Template cannot be None")
    field_names = extract_template_field_names(template)
    values = {
        field_name: extract_property(
            item, field_name, fail_on_missing=fail_on_missing, default=default
        )
        for field_name in field_names
    }
    return fill_template(template, values)


@registry.register_segment("copy")
@segment
def copy_segment(items: Iterable[Any]) -> Iterator[Any]:
    """Create shallow copies of each item in the pipeline.

    This segment creates a shallow copy of each item, suitable when you need to
    prevent downstream modifications from affecting the original items. Shallow
    copies share references to nested objects (lists, dicts within dicts), so
    modifications to nested structures will still affect originals.

    Use deepCopy instead if you need complete independence from the originals,
    though deepCopy is slower and more memory-intensive.

    Useful for:
    - Preventing accidental mutations in complex pipelines
    - Creating independent item instances before modification
    - Preserving original data while processing

    Yields:
        Shallow copies of each input item.
    """
    for item in items:
        yield copy.copy(item)


@registry.register_segment("deepCopy")
@segment
def deep_copy_segment(items: Iterable[Any]) -> Iterator[Any]:
    """Create complete independent deep copies of each item in the pipeline.

    This segment creates a deep copy of each item, recursively copying all nested
    structures (lists, dicts, and objects within them). This ensures complete
    independence from the originals - modifications to any nested structure won't
    affect the original items.

    Deep copy is slower and more memory-intensive than shallow copy. Use copy
    instead if nested structures don't need to be independent.

    Useful for:
    - Complex nested data that will be heavily modified
    - When you need complete independence from original data
    - Pipelines where multiple branches process the same item

    Yields:
        Deep copies of each input item.
    """
    for item in items:
        yield copy.deepcopy(item)
