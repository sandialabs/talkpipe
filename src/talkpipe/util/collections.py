"""Collection utilities: adaptive buffers and expiring key-value stores.

Provides AdaptiveBuffer for rate-aware batching and ExpiringDict for
in-memory caches with optional TTL and persistence.
"""

import json
import logging
import os
import time
from collections import UserDict
from collections.abc import Callable, ItemsView, Iterable, KeysView, ValuesView
from typing import Any

logger = logging.getLogger(__name__)


class AdaptiveBuffer:
    """Buffer that adapts its flush size based on item arrival rate.

    When items arrive quickly (intervals <= fast_interval), flushes at max_size
    for efficiency. When items arrive slowly (intervals >= slow_interval),
    flushes at min_size for responsiveness. Uses EMA of inter-arrival intervals
    to interpolate target size between these extremes.
    """

    def __init__(
        self,
        max_size: int = 1000,
        min_size: int = 1,
        fast_interval: float = 0.05,
        slow_interval: float = 1.0,
        smoothing: float = 0.2,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """Initialize the buffer with size and timing parameters."""
        if min_size < 1:
            raise ValueError("min_size must be >= 1")
        if max_size < min_size:
            raise ValueError("max_size must be >= min_size")
        if fast_interval <= 0:
            raise ValueError("fast_interval must be > 0")
        if slow_interval <= fast_interval:
            raise ValueError("slow_interval must be > fast_interval")
        if not 0 < smoothing <= 1:
            raise ValueError("smoothing must be in (0, 1]")

        self.max_size = max_size
        self.min_size = min_size
        self.fast_interval = fast_interval
        self.slow_interval = slow_interval
        self.smoothing = smoothing
        self.time_func = time_func

        self._buffer: list[Any] = []
        self._last_append_time: float | None = None
        self._ema_interval: float | None = None
        self._target_size: int = min_size

    def append(self, item: Any) -> list[Any] | None:
        """Add an item; returns flushed batch if target size reached, else None."""
        now = self.time_func()
        if self._last_append_time is not None:
            interval = max(0.0, now - self._last_append_time)
            self._update_interval(interval)
            self._target_size = self._compute_target_size()
        self._last_append_time = now

        self._buffer.append(item)
        if len(self._buffer) >= self._target_size:
            return self.flush()
        return None

    def extend(self, items: Iterable[Any]) -> list[list[Any]]:
        """Add multiple items; returns list of any flushed batches."""
        flushed: list[list[Any]] = []
        for item in items:
            batch = self.append(item)
            if batch is not None:
                flushed.append(batch)
        return flushed

    def flush(self) -> list[Any] | None:
        """Force flush and return all buffered items, or None if empty."""
        if not self._buffer:
            return None
        items = self._buffer
        self._buffer = []
        return items

    def __len__(self) -> int:
        return len(self._buffer)

    def _update_interval(self, interval: float) -> None:
        """Update EMA of inter-arrival interval using smoothing factor."""
        if self._ema_interval is None:
            self._ema_interval = interval
        else:
            alpha = self.smoothing
            self._ema_interval = (alpha * interval) + ((1 - alpha) * self._ema_interval)

    def _compute_target_size(self) -> int:
        """Compute target flush size from EMA interval (min_size to max_size)."""
        if self._ema_interval is None:
            return self.min_size
        if self._ema_interval <= self.fast_interval:
            return self.max_size
        if self._ema_interval >= self.slow_interval:
            return self.min_size

        # Linear interpolation: faster arrivals -> larger target
        ratio = (self.slow_interval - self._ema_interval) / (
            self.slow_interval - self.fast_interval
        )
        target = self.min_size + round(ratio * (self.max_size - self.min_size))
        return max(self.min_size, min(self.max_size, target))


class ExpiringDict(UserDict[Any, Any]):
    """Dict-like store with per-key TTL and optional JSON persistence.

    Keys expire after their TTL (seconds). If filename is set, the dict is
    saved to disk on every mutation and loaded on init.
    """

    def __init__(
        self,
        filename: str | os.PathLike[str] | None = None,
        default_ttl: float | None = None,
    ) -> None:
        """Initialize with optional persistence path and default TTL in seconds."""
        super().__init__()
        self.default_ttl = default_ttl
        self.filename = filename
        self.expiry: dict[Any, float] = {}

        if filename:
            self._load()

    def __setitem__(self, key: Any, value: Any, ttl: float | None = None) -> None:
        """Set key to value; ttl overrides default_ttl if provided."""
        self.data[key] = value

        if ttl is None:
            ttl = self.default_ttl

        if ttl is not None:
            self.expiry[key] = time.time() + ttl

        if self.filename:
            self._save()  # Save when a key is set

    def __delitem__(self, key: Any) -> None:
        """Delete key and its expiry entry."""
        super().__delitem__(key)
        if key in self.expiry:
            del self.expiry[key]

        if self.filename:
            self._save()  # Save when a key is deleted

    def __getitem__(self, key: Any) -> Any:
        """Get value; raises KeyError if missing or expired."""
        self._clean_expired()
        if key in self.expiry and time.time() > self.expiry[key]:
            del self.data[key]
            del self.expiry[key]
            if self.filename:
                self._save()  # Save after removing expired keys
            raise KeyError(key)
        return self.data[key]

    def set_with_ttl(self, key: Any, value: Any, ttl: float | None) -> None:
        """Convenience method to set a key with explicit TTL."""
        self.__setitem__(key, value, ttl)

    def clear(self) -> None:
        super().clear()
        self.expiry.clear()
        if self.filename:
            self._save()  # Save after clearing

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        if self.filename:
            self._save()  # Save after update

    def pop(self, key: Any, *args: Any) -> Any:
        result = super().pop(key, *args)
        if key in self.expiry:
            del self.expiry[key]
        if self.filename:
            self._save()  # Save after pop
        return result

    def popitem(self) -> tuple[Any, Any]:
        key, value = super().popitem()
        if key in self.expiry:
            del self.expiry[key]
        if self.filename:
            self._save()  # Save after popitem
        return key, value

    def _clean_expired(self) -> None:
        """Remove all expired keys from data and expiry maps."""
        now = time.time()
        expired = [k for k, exp in self.expiry.items() if now > exp]
        if expired:  # Only save if something was expired
            for k in expired:
                if k in self.data:
                    del self.data[k]
                del self.expiry[k]
            if self.filename:
                self._save()  # Save after cleaning expired keys

    def keys(self) -> KeysView[Any]:
        self._clean_expired()
        return self.data.keys()

    def values(self) -> ValuesView[Any]:
        self._clean_expired()
        return self.data.values()

    def items(self) -> ItemsView[Any, Any]:
        self._clean_expired()
        return self.data.items()

    def __len__(self) -> int:
        self._clean_expired()
        return len(self.data)

    def __contains__(self, key: object) -> bool:
        self._clean_expired()
        return key in self.data

    def _save(self) -> None:
        """Persist data and expiry to JSON file via atomic write."""
        if self.filename:
            # Use .tmp file and atomic rename for safety
            tmp_filename = str(self.filename) + ".tmp"
            data_to_save = {"data": self.data, "expiry": self.expiry}
            try:
                with open(tmp_filename, "w") as f:
                    json.dump(data_to_save, f)
                os.rename(
                    tmp_filename, str(self.filename)
                )  # Atomic on most filesystems
            except Exception:
                if os.path.exists(tmp_filename):
                    os.unlink(tmp_filename)
                raise

    def _load(self) -> None:
        """Load data and expiry from JSON file; on failure, start empty."""
        try:
            if self.filename is not None and os.path.exists(self.filename):
                with open(self.filename) as f:
                    loaded_data = json.load(f)
                self.data = loaded_data.get("data", {})
                self.expiry = loaded_data.get("expiry", {})
                self._clean_expired()
            else:
                self.data = {}
                self.expiry = {}
        except Exception as e:
            logger.warning(
                f"Failed to load cached data from {self.filename}: {e}. Starting with empty cache."
            )
            self.data = {}
            self.expiry = {}
