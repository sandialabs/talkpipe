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

The module also re-exports the names the pre-split module pulled in for its
own use — the segment base classes and decorators from
:mod:`talkpipe.pipe.core` and the helpers from :mod:`talkpipe.util` — because
downstream code imported them from here too.

New code should import from the themed module.
"""

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.collect import ToDataFrame, ToList
from talkpipe.pipe.core import (
    AbstractFieldSegment,
    AbstractSegment,
    field_segment,
    segment,
    source,
)
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
from talkpipe.util.config import configure_logger, get_config, parse_key_value_str
from talkpipe.util.data_manipulation import (
    assign_property,
    compileLambda,
    dict_to_text,
    extract_property,
    extract_template_field_names,
    fill_template,
    get_all_attributes,
    get_type_safely,
    toDict,
)
from talkpipe.util.os import run_command

__all__ = [
    "AbstractFieldSegment",
    "AbstractSegment",
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
    "assign_property",
    "compileLambda",
    "concat",
    "configure_logger",
    "copy_segment",
    "deep_copy_segment",
    "dict_to_text",
    "everyN",
    "exec",
    "extractProperty",
    "extract_property",
    "extract_template_field_names",
    "field_segment",
    "fillTemplate",
    "fill_template",
    "firstN",
    "flatten",
    "get_all_attributes",
    "get_config",
    "get_type_safely",
    "hash_data",
    "isFalse",
    "isIn",
    "isNotIn",
    "isTrue",
    "longestStr",
    "parse_key_value_str",
    "progressTicks",
    "registry",
    "run_command",
    "segment",
    "setAs",
    "sleep",
    "slice",
    "source",
    "toDict",
]
