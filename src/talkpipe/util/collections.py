import json
import logging
import os
import time
from collections import UserDict

logger = logging.getLogger(__name__)

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

