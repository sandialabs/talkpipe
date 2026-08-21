"""Shell integration: run a command and stream its output."""

from collections.abc import Iterator
from typing import Annotated

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    source,
)
from talkpipe.util.os import run_command


@registry.register_source(name="exec")
@source()
def exec(command: Annotated[str, "The shell command to execute."]) -> Iterator[str]:
    """Execute a shell command and yield each line from stdout as a data item.

    This source allows you to integrate shell commands into TalkPipe pipelines,
    streaming the output line by line for further processing.

    ChatterLang Usage:
        input exec[command="ls -la"]
        input exec[command="find /path -name '*.txt'"]

    Args:
        command (str): The shell command to execute.

    Yields:
        str: Each line from the command's stdout output.
    """
    yield from run_command(command)
