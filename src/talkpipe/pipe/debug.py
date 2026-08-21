"""Diagnostic and observability segments: inspect, count, and log what flows through a pipeline."""

import logging
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Annotated, Any

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    AbstractSegment,
    segment,
)
from talkpipe.util.config import configure_logger, get_config
from talkpipe.util.data_manipulation import (
    compileLambda,
    get_all_attributes,
    toDict,
)


@registry.register_segment("diagPrint")
@segment()
def DiagPrint(
    items: Iterable[Any],
    field_list: Annotated[
        str,
        "Comma-separated fields to extract in form 'field[:new_name],...' where _ means the whole item",
    ] = "_",
    label: Annotated[
        str | None, "Optional label to print below the separator each time."
    ] = None,
    expression: Annotated[
        str | None,
        "A Python expression using 'item' as the variable (e.g., 'item * 2')",
    ] = None,
    output: Annotated[
        str | None,
        "If 'stderr', output to stderr.  If 'stdout', output to stdout.  Otherwise write to a logger with this name.  If None or the string 'None', do not write output.",
    ] = "stdout",
    level: Annotated[
        str | int, "Logging level (name or number) if output is to a logger."
    ] = "DEBUG",
) -> Iterator[Any]:
    """
    Print pass-through diagnostics for each item in a stream.

    Behavior:
    - Emits a separator, optional label, elapsed time since the last item, type, and value.
    - Optionally prints selected fields (`field_list`) and an evaluated expression (`expression`).
    - Always yields the original items unchanged.

    Output routing:
    - `stdout` (default) prints to standard output.
    - `stderr` prints to standard error.
    - Any other string is treated as a logger name; messages are emitted at `level`.
    - `None` or `"None"` disables all output.
    - `config:<key>` looks up the target (stdout, stderr, or logger name) from `get_config()[<key>]`.

    Common uses:
    - Quick inspection while composing pipelines.
    - Lightweight timing between items (elapsed time column).
    - Field-focused debugging by passing `field_list="a,b,c"` to avoid dumping entire items.
    - Expression checks, e.g. `expression="item['score'] > 0.8"`.

    Examples:
    - Pipe API: `DiagPrint(label="chunk", field_list="id,text", output="stderr")`
    - ChatterLang: `| diagPrint[label="chunk", field_list="id,text", expression="len(item['text'])"]`
    - Config-driven: set `diag_output="stderr"` in your config, then use `output="config:diag_output"`.
    """
    # Track elapsed time between calls for this DiagPrint instance
    last_time: float | None = None
    output_fn: Callable[[str], Any] | None
    if output is None or output.lower() == "none":
        output_fn = None
    else:
        if output.lower().startswith("config:"):
            output = get_config().get(output[len("config:") :].strip(), None)
        if output and output.lower() == "stderr":

            def output_fn(msg: str) -> Any:
                return print(msg, file=sys.stderr, flush=True)
        elif output and output.lower() == "stdout":

            def output_fn(msg: str) -> Any:
                return print(msg, file=sys.stdout, flush=True)
        else:

            def output_fn(msg: str) -> Any:
                return logging.getLogger(output).log(
                    msg=msg,
                    level=logging.getLevelName(level.upper())
                    if isinstance(level, str)
                    else level,
                )

    if expression:
        f = compileLambda(expression)

    for item in items:
        if output_fn:
            now = time.perf_counter()
            elapsed_str = "0.000s" if last_time is None else f"{now - last_time:.3f}s"
            last_time = now
            output_fn("================================")
            if label:
                output_fn(label)
            output_fn(f"Elapsed: {elapsed_str} since last call")
            output_fn(f"Type: {type(item)}")
            if field_list != "_":
                output_fn("-------\nFields:")
                item_dict = toDict(item, field_list=field_list, fail_on_missing=False)
                for key, value in item_dict.items():
                    output_fn(f"{key}: {value}")
            else:
                output_fn("-------\nValue:")
                output_fn(f"{item}")
            if expression:
                output_fn("-------\nExpression:")
                output_fn(f"{expression} = {f(item)}")
        yield item


@registry.register_segment(name="progressTicks")
@segment()
def progressTicks(
    items: Iterable[Any],
    tick: Annotated[str, "The character to print as a tick mark."] = ".",
    tick_count: Annotated[
        int, "Number of items to process before printing a tick mark."
    ] = 10,
    eol_count: Annotated[
        int | None,
        "Number of tick marks before starting a new line. If None, no new line is printed.",
    ] = 10,
    print_count: Annotated[
        bool, "If True, prints the count of items processed at line ends."
    ] = False,
) -> Iterator[Any]:
    """Display progress indicators while processing items in the pipeline.

    Prints tick marks to stderr to visualize processing progress without interfering
    with the main data stream. Useful for monitoring long-running pipelines.

    ChatterLang Usage:
        progressTicks[tick="*", tick_count=100, eol_count=10, print_count=true]

    Yields:
        Any: The original items from the input iterable, unchanged.
    """
    count = 0
    for idx, item in enumerate(items, 1):
        if idx % tick_count == 0 and idx != 0:
            print(tick, end="", flush=True, file=sys.stderr)
            if eol_count and (idx // tick_count) % eol_count == 0:
                if print_count:
                    print(f"{idx}", end="", flush=True, file=sys.stderr)
                print(file=sys.stderr)
        count = idx
        yield item
    if print_count:
        print(f"\nTotal items processed: {count}", file=sys.stderr)


@registry.register_segment(name="describe")
class DescribeData(AbstractSegment[Any, Any]):
    """Returns a dictionary of all attributes of the input data.

    This is useful mostly for debugging and understanding the
    structure of the data.
    """

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        for data in input_iter:
            yield get_all_attributes(data)


@registry.register_segment("configureLogger")
class ConfigureLogger(AbstractSegment[Any, Any]):
    """Configures loggers based on the provided logger levels and files.

    This segment configures loggers based on the provided logger levels and files.
    The logger levels are specified as a string in the format "logger:level,logger:level,...".
    The logger files are specified as a string in the format "logger:file,logger:file,...".

    It configures when the script is compiled or the object is instantiated and never again
    after that.  It passes the input data through unchanged.

    Args:
        logger_levels (str): Logger levels in format 'logger:level,logger:level,...'
        logger_files (str): Logger files in format 'logger:file,logger:file,...'
    """

    def __init__(
        self,
        logger_levels: Annotated[
            str | None, "Logger levels in format 'logger:level,logger:level,...'"
        ] = None,
        logger_files: Annotated[
            str | None, "Logger files in format 'logger:file,logger:file,...'"
        ] = None,
    ):
        super().__init__()
        self.logger_levels = logger_levels
        self.logger_files = logger_files
        configure_logger(self.logger_levels, logger_files=self.logger_files)

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Configure loggers based on the provided logger levels and files.

        Args:
            input_iter (Iterable): The input data
        """
        yield from input_iter
