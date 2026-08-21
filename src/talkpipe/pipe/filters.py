"""Predicate and expression segments: test, filter, and evaluate Python expressions on items."""

import logging
from collections.abc import Callable, Iterable, Iterator
from typing import Annotated, Any

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    AbstractFieldSegment,
    AbstractSegment,
    segment,
)
from talkpipe.util.data_manipulation import (
    assign_property,
    compileLambda,
    extract_property,
)

logger = logging.getLogger(__name__)


def _bool_filter_transform(
    items: Iterable[Any],
    field: str,
    predicate: Callable[[Any], bool],
    as_filter: bool,
    set_as: str | None,
) -> Iterator[Any]:
    """Common logic for isIn, isNotIn, isTrue, isFalse segments."""
    for item in items:
        value = extract_property(item, field)
        ans = predicate(value)
        if set_as:
            assign_property(item, set_as, ans)
            to_return = item
        else:
            to_return = item if as_filter else ans
        if not as_filter or ans:
            yield to_return


def _is_truthy(value: Any) -> bool:
    """Check if value is truthy (not None, False, 0, or empty string)."""
    return (
        bool(value)
        and (value != 0)
        and (not isinstance(value, str) or len(value.strip()) > 0)
    )


@registry.register_segment("isIn")
@segment()
def isIn(
    items: Iterable[Any],
    field: Annotated[str, "Field name to check for value"],
    value: Annotated[Any, "Value to check for in the field"],
    as_filter: Annotated[
        bool,
        "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true.",
    ] = True,
    set_as: Annotated[
        str | None, "If specified, the result will be added to this field in the item."
    ] = None,
) -> Iterator[Any]:
    """Check if a field contains a value, optionally filtering items.

    Tests whether a specified value is contained in a field using Python's 'in' operator.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the condition is true
    - Boolean mode (as_filter=False): yields boolean results for all items

    Useful for searching strings for substrings, checking list membership, or
    checking dictionary key existence.

    Yields:
        In filter mode: items where value is in the field.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    yield from _bool_filter_transform(
        items, field, lambda v: value in v, as_filter, set_as
    )


@registry.register_segment("isNotIn")
@segment()
def isNotIn(
    items: Iterable[Any],
    field: Annotated[str, "Field name to check for value"],
    value: Annotated[Any, "Value to check for in the field"],
    as_filter: Annotated[
        bool,
        "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true.",
    ] = True,
    set_as: Annotated[
        str | None, "If specified, the result will be added to this field in the item."
    ] = None,
) -> Iterator[Any]:
    """Check if a field does not contain a value, optionally filtering items.

    Tests whether a specified value is NOT contained in a field using Python's 'not in' operator.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the condition is true
    - Boolean mode (as_filter=False): yields boolean results for all items

    Useful for excluding items with specific patterns, filtering out unwanted strings,
    or checking that values are absent.

    Yields:
        In filter mode: items where value is NOT in the field.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    yield from _bool_filter_transform(
        items, field, lambda v: value not in v, as_filter, set_as
    )


@registry.register_segment("isTrue")
@segment()
def isTrue(
    items: Iterable[Any],
    as_filter: Annotated[
        bool,
        "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true.",
    ] = True,
    field: Annotated[
        str,
        "The field to check for truthiness. Defaults to '_', which means the entire item.",
    ] = "_",
    set_as: Annotated[
        str | None, "If specified, the result will be added to this field in the item."
    ] = None,
) -> Iterator[Any]:
    """Check if a field is truthy, optionally filtering items.

    Tests whether the specified field is considered true. A value is considered false
    if it is None, False, an integer 0, or an empty string. All other values are true.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the field is truthy
    - Boolean mode (as_filter=False): yields boolean results for all items

    Useful for filtering items by presence of content, non-empty fields, or truthy values.

    Yields:
        In filter mode: items where the field is truthy.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    yield from _bool_filter_transform(items, field, _is_truthy, as_filter, set_as)


@registry.register_segment("isFalse")
@segment()
def isFalse(
    items: Iterable[Any],
    as_filter: Annotated[
        bool,
        "Whether to use this function as a filter. If false, only return True or False. If true, yield the item if the condition is true.",
    ] = True,
    field: Annotated[
        str,
        "The field to check for falsiness. Defaults to '_', which means the entire item.",
    ] = "_",
    set_as: Annotated[
        str | None, "If specified, the result will be added to this field in the item."
    ] = None,
) -> Iterator[Any]:
    """Check if a field is falsy, optionally filtering items.

    Tests whether the specified field is considered false. A value is considered false
    if it is None, False, an integer 0, or an empty string. All other values are true.
    Can operate in two modes:
    - Filter mode (as_filter=True): yields items where the field is falsy
    - Boolean mode (as_filter=False): yields boolean results for all items

    Useful for filtering items with missing data, empty fields, or falsy values.

    Yields:
        In filter mode: items where the field is falsy.
        In boolean mode: True/False for each item.
        If set_as is specified: item with boolean result added as new field.
    """
    yield from _bool_filter_transform(
        items, field, lambda v: not _is_truthy(v), as_filter, set_as
    )


@registry.register_segment("lambda")
class EvalExpression(AbstractFieldSegment[Any, Any]):
    """Evaluate a Python expression on each item in the input stream.

    This segment pre-compiles the expression during initialization for efficiency
    and then applies it to each item during transformation. Expressions are evaluated
    in a restricted environment for security.

    The item is available in expressions as 'item'.
    """

    def __init__(
        self,
        expression: Annotated[str, "The Python expression to evaluate"],
        field: Annotated[
            str | None,
            "If provided, extract this field from each item before evaluating",
        ] = "_",
        set_as: Annotated[
            str | None,
            "If provided, append the result to each item under this field name",
        ] = None,
    ):
        super().__init__()
        self.expression = expression
        self.field = field
        self.set_as = set_as

        # Compile the expression into a lambda function
        self.lambda_function = compileLambda(expression)

    def process_value(self, value: Any) -> Any:
        try:
            return self.lambda_function(value)
        except Exception as e:
            logger.error(
                f"Error evaluating expression '{self.expression}' on value '{value}': {e}"
            )
            raise


@registry.register_segment("lambdaFilter")
class FilterExpression(AbstractSegment[Any, Any]):
    """Filter items from the input stream based on a Python expression.

    This segment pre-compiles the expression during initialization for efficiency
    and then applies it to each item during transformation. Expressions are evaluated
    in a restricted environment for security.

    The item is available in expressions as 'item'. If the item is a dictionary,
    its fields can be accessed directly as variables in the expression.

    """

    def __init__(
        self,
        expression: Annotated[str, "The Python expression to evaluate"],
        field: Annotated[
            str | None,
            "If provided, extract this field from each item before evaluating",
        ] = "_",
    ):
        super().__init__()
        self.expression = expression
        self.field = field

        # Compile the expression into a lambda function
        self.lambda_function = compileLambda(expression)

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Process each item from the input stream."""
        for item in input_iter:
            value = extract_property(item, self.field) if self.field else item
            if self.lambda_function(value):
                yield item
