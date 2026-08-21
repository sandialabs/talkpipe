"""Hashing of items and selected fields."""

import hashlib
import json
import logging
from collections.abc import Iterable, Iterator
from typing import Annotated, Any

import talkpipe.chatterlang.registry as registry
from talkpipe.pipe.core import (
    AbstractSegment,
)
from talkpipe.util.config import parse_key_value_str
from talkpipe.util.data_manipulation import (
    assign_property,
    extract_property,
)

logger = logging.getLogger(__name__)


_SECURE_HASH_ALGOS = frozenset(
    {
        "SHA224",
        "SHA256",
        "SHA384",
        "SHA512",
        "SHA3_224",
        "SHA3_256",
        "SHA3_384",
        "SHA3_512",
    }
)


def _validate_hash_algorithm(algorithm: str) -> None:
    """Raise ValueError if algorithm is insecure or unsupported."""
    if algorithm.upper() in {"MD5", "SHA1"} or algorithm.upper() not in {
        a.upper() for a in _SECURE_HASH_ALGOS
    }:
        raise ValueError(
            f"Unsupported or insecure hash algorithm: {algorithm}. Allowed: {', '.join(sorted(_SECURE_HASH_ALGOS))}"
        )


def hash_data(
    data: Any,
    algorithm: Annotated[
        str,
        "Hash algorithm to use. Options include SHA1, SHA224, SHA256, SHA384, SHA512, SHA-3, and MD5.",
    ] = "SHA256",
    field_list: Annotated[
        str | list[str], "List of fields to include in the hash"
    ] = "_",
    use_repr: Annotated[
        bool,
        "Whether to use repr() or JSON serialization. Defaults to True for security.",
    ] = True,
    fail_on_missing: Annotated[bool, "Whether to fail on missing fields"] = True,
    default: Annotated[Any, "Default value to use for missing fields"] = None,
) -> str:
    """Hash a single data item using the specified parameters.

    Returns:
        str: The resulting hash digest
    """
    fields = (
        list(parse_key_value_str(field_list).keys())
        if isinstance(field_list, str)
        else field_list
    )
    _validate_hash_algorithm(algorithm)
    hasher = hashlib.new(algorithm)
    for field in fields:
        item = extract_property(data, field, fail_on_missing, default=default)
        if item is None:
            if fail_on_missing:
                raise ValueError(f"Field {field} value was None")
            logger.warning(f"Field {field} value was None. Ignoring")
            continue

        if use_repr:
            # Safe: repr() doesn't execute code and works with all objects
            hasher.update(repr(item).encode("utf-8"))
        else:
            # Safe: JSON serialization instead of pickle
            try:
                # Use JSON with sorted keys for deterministic hashing
                json_str = json.dumps(
                    item, sort_keys=True, default=str, ensure_ascii=False
                )
                hasher.update(json_str.encode("utf-8"))
            except (TypeError, ValueError) as e:
                # Fallback to repr for non-JSON-serializable objects
                logger.debug(
                    f"JSON serialization failed for {type(item)}, using repr: {e}"
                )
                hasher.update(repr(item).encode("utf-8"))

    return hasher.hexdigest()


@registry.register_segment("hash")
class Hash(AbstractSegment[Any, Any]):
    """Hashes the input data using the specified algorithm.

    This segment hashes the input data using the specified algorithm.
    All datatypes are hashed using either repr() or JSON serialization for security.

    """

    def __init__(
        self,
        algorithm: Annotated[
            str,
            "Hash algorithm to use. Options include SHA1, SHA224, SHA256, SHA384, SHA512, SHA-3, and MD5.",
        ] = "SHA256",
        use_repr: Annotated[
            bool,
            "Whether to use repr() or JSON serialization. Defaults to True for security.",
        ] = True,
        field_list: Annotated[str, "List of fields to include in the hash"] = "_",
        set_as: str | None = None,
        fail_on_missing: Annotated[bool, "Whether to fail on missing fields"] = True,
    ):
        super().__init__()
        _validate_hash_algorithm(algorithm)
        self.algorithm = algorithm
        self.use_repr = use_repr
        self.field_list = list(parse_key_value_str(field_list).keys())
        self.fail_on_missing = fail_on_missing
        self.set_as = set_as

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Hash the input data using the specified algorithm.

        Args:
            input_iter (Iterable): The input data
        """
        for data in input_iter:
            digest = hash_data(
                data,
                self.algorithm,
                self.field_list,
                self.use_repr,
                self.fail_on_missing,
            )
            if self.set_as:
                assign_property(data, self.set_as, digest)
                yield data
            else:
                yield digest
