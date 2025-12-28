import json
import logging
import os
import time
from collections import UserDict

logger = logging.getLogger(__name__)

class AdaptiveBuffer:
    """Buffer that adapts its flush size based on item arrival rate."""

    def __init__(
        self,
        max_size=1000,
        min_size=1,
        fast_interval=0.05,
        slow_interval=1.0,
        smoothing=0.2,
        time_func=time.time,
    ):
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

        self._buffer = []
        self._last_append_time = None
        self._ema_interval = None
        self._target_size = min_size

    def append(self, item):
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

    def extend(self, items):
        flushed = []
        for item in items:
            batch = self.append(item)
            if batch is not None:
                flushed.append(batch)
        return flushed

    def flush(self):
        if not self._buffer:
            return None
        items = self._buffer
        self._buffer = []
        return items

    def __len__(self):
        return len(self._buffer)

    def _update_interval(self, interval):
        if self._ema_interval is None:
            self._ema_interval = interval
        else:
            alpha = self.smoothing
            self._ema_interval = (alpha * interval) + ((1 - alpha) * self._ema_interval)

    def _compute_target_size(self):
        if self._ema_interval is None:
            return self.min_size
        if self._ema_interval <= self.fast_interval:
            return self.max_size
        if self._ema_interval >= self.slow_interval:
            return self.min_size

        ratio = (self.slow_interval - self._ema_interval) / (
            self.slow_interval - self.fast_interval
        )
        target = self.min_size + int(round(ratio * (self.max_size - self.min_size)))
        print(target)
        return max(self.min_size, min(self.max_size, target))


class ExpiringDict(UserDict):
    def __init__(self, filename=None, default_ttl=None):
        super().__init__()
        self.default_ttl = default_ttl
        self.filename = filename
        self.expiry = {}
        
        if filename:
            self._load()
    
    def __setitem__(self, key, value, ttl=None):
        self.data[key] = value
        
        if ttl is None:
            ttl = self.default_ttl
            
        if ttl is not None:
            self.expiry[key] = time.time() + ttl
            
        if self.filename:
            self._save()  # Save when a key is set
    
    def __delitem__(self, key):
        super().__delitem__(key)
        if key in self.expiry:
            del self.expiry[key]
            
        if self.filename:
            self._save()  # Save when a key is deleted
    
    def __getitem__(self, key):
        self._clean_expired()
        if key in self.expiry and time.time() > self.expiry[key]:
            del self.data[key]
            del self.expiry[key]
            if self.filename:
                self._save()  # Save after removing expired keys
            raise KeyError(key)
        return self.data[key]
    
    def set_with_ttl(self, key, value, ttl):
        self.__setitem__(key, value, ttl)
    
    def clear(self):
        super().clear()
        self.expiry.clear()
        if self.filename:
            self._save()  # Save after clearing
    
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        if self.filename:
            self._save()  # Save after update
    
    def pop(self, key, *args):
        result = super().pop(key, *args)
        if key in self.expiry:
            del self.expiry[key]
        if self.filename:
            self._save()  # Save after pop
        return result
    
    def popitem(self):
        key, value = super().popitem()
        if key in self.expiry:
            del self.expiry[key]
        if self.filename:
            self._save()  # Save after popitem
        return key, value
    
    def _clean_expired(self):
        """Remove all expired keys"""
        now = time.time()
        expired = [k for k, exp in self.expiry.items() if now > exp]
        if expired:  # Only save if something was expired
            for k in expired:
                if k in self.data:
                    del self.data[k]
                del self.expiry[k]
            if self.filename:
                self._save()  # Save after cleaning expired keys
    
    def keys(self):
        self._clean_expired()
        return self.data.keys()
    
    def values(self):
        self._clean_expired()
        return self.data.values()
    
    def items(self):
        self._clean_expired()
        return self.data.items()
    
    def __len__(self):
        self._clean_expired()
        return len(self.data)
    
    def __contains__(self, key):
        self._clean_expired()
        return key in self.data
    
    def _save(self):
        if self.filename:
            # Use .tmp file and atomic rename for safety
            tmp_filename = str(self.filename) + '.tmp'
            data_to_save = {
                'data': self.data,
                'expiry': self.expiry
            }
            try:
                with open(tmp_filename, 'w') as f:
                    json.dump(data_to_save, f)
                os.rename(tmp_filename, str(self.filename))  # Atomic on most filesystems
            except Exception:
                if os.path.exists(tmp_filename):
                    os.unlink(tmp_filename)
                raise
    
    def _load(self):
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r') as f:
                    loaded_data = json.load(f)
                self.data = loaded_data.get('data', {})
                self.expiry = loaded_data.get('expiry', {})
                self._clean_expired()
            else:
                self.data = {}
                self.expiry = {}
        except Exception as e:
            logger.warning(f"Failed to load cached data from {self.filename}: {e}. Starting with empty cache.")
            self.data = {}
            self.expiry = {}
