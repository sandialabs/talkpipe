"""Standard operations for data processing pipelines.

This module is kept as a compatibility facade: the segments that used to be
defined here now live in themed modules, and every public name is re-exported
so ``from talkpipe.pipe.basic import X`` and ``from talkpipe.pipe.basic
import *`` keep working.

- :mod:`talkpipe.pipe.debug` — ``diagPrint``, ``describe``, ``progressTicks``,
  ``configureLogger``
- :mod:`talkpipe.pipe.flow` — ``sleep``, ``firstN``, ``everyN``, ``debounce``
- :mod:`talkpipe.pipe.fields` — ``cast``, ``toDict``, ``formatItem``,
  ``setAs``, ``extractProperty``, ``set``, ``concat``, ``slice``,
  ``longestStr``, ``flatten``, ``fillTemplate``, ``copy``, ``deepCopy``
- :mod:`talkpipe.pipe.filters` — ``isIn``, ``isNotIn``, ``isTrue``,
  ``isFalse``, ``lambda``, ``lambdaFilter``
- :mod:`talkpipe.pipe.collect` — ``toList``, ``toDataFrame``
- :mod:`talkpipe.pipe.hashing` — ``hash`` and :func:`hash_data`
- :mod:`talkpipe.pipe.shell` — the ``exec`` source

New code should import from the themed module.
"""

from talkpipe.pipe.collect import ToDataFrame, ToList
from talkpipe.pipe.debug import ConfigureLogger, DescribeData, DiagPrint, progressTicks
from talkpipe.pipe.fields import (
    Cast,
    FormattedItem,
    ToDict,
    assign,
    concat,
    copy_segment,
    deep_copy_segment,
    extractProperty,
    fillTemplate,
    flatten,
    longestStr,
    setAs,
    slice,
)
from talkpipe.pipe.filters import (
    EvalExpression,
    FilterExpression,
    isFalse,
    isIn,
    isNotIn,
    isTrue,
)
from talkpipe.pipe.flow import Debounce, everyN, firstN, sleep
from talkpipe.pipe.hashing import Hash, hash_data
from talkpipe.pipe.shell import exec

__all__ = [
    "Cast",
    "ConfigureLogger",
    "Debounce",
    "DescribeData",
    "DiagPrint",
    "EvalExpression",
    "FilterExpression",
    "FormattedItem",
    "Hash",
    "ToDataFrame",
    "ToDict",
    "ToList",
    "assign",
    "concat",
    "copy_segment",
    "deep_copy_segment",
    "everyN",
    "exec",
    "extractProperty",
    "fillTemplate",
    "firstN",
    "flatten",
    "hash_data",
    "isFalse",
    "isIn",
    "isNotIn",
    "isTrue",
    "longestStr",
    "progressTicks",
    "setAs",
    "sleep",
    "slice",
]
