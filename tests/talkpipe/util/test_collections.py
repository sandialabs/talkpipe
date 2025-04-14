import pytest
import time
import os
import tempfile
from unittest.mock import patch
from talkpipe.util.collections import ExpiringDict


def test_init(tmp_path):
    # Test initialization without parameters
    d = ExpiringDict()
    assert len(d) == 0
    assert d.default_ttl is None
    assert d.filename is None
    
    # Test initialization with default TTL
    d = ExpiringDict(default_ttl=10)
    assert len(d) == 0
    assert d.default_ttl == 10
    
    # Test initialization with filename
    with patch('talkpipe.util.collections.ExpiringDict._load') as mock_load:
        temp_filename = tmp_path / "test_shelve_file"
        d = ExpiringDict(filename=temp_filename)
        assert d.filename == temp_filename
        mock_load.assert_called_once()


def test_setitem(tmp_path):
    d = ExpiringDict()
    
    # Test basic set
    d['key1'] = 'value1'
    assert d['key1'] == 'value1'
    assert 'key1' not in d.expiry
    
    # Test set with default TTL
    d = ExpiringDict(default_ttl=10)
    start_time = time.time()
    d['key1'] = 'value1'
    assert d['key1'] == 'value1'
    assert 'key1' in d.expiry
    assert d.expiry['key1'] - (start_time + 10) < 1  # Allow small delta
    
    # Test set with specific TTL
    start_time = time.time()
    d.__setitem__('key2', 'value2', ttl=20)
    assert d['key2'] == 'value2'
    assert 'key2' in d.expiry
    assert d.expiry['key2'] - (start_time + 20) < 1  # Allow small delta
    
    # Test set_with_ttl method
    start_time = time.time()
    d.set_with_ttl('key3', 'value3', ttl=30)
    assert d['key3'] == 'value3'
    assert 'key3' in d.expiry
    assert d.expiry['key3'] - (start_time + 30) < 1  # Allow small delta
    
    # Test that _save is called when filename is set
    with patch('talkpipe.util.collections.ExpiringDict._save') as mock_save:
        temp_filename = tmp_path / "test_file"
        d = ExpiringDict(filename=temp_filename)
        d['key1'] = 'value1'
        mock_save.assert_called_once()


def test_getitem_expiry():
    d = ExpiringDict()
    
    # Test getting a non-existent key
    with pytest.raises(KeyError):
        value = d['nonexistent']
    
    # Test getting a key that has not expired
    d.set_with_ttl('key1', 'value1', ttl=10)
    assert d['key1'] == 'value1'
    
    # Test getting a key that has expired
    d.set_with_ttl('key2', 'value2', ttl=0.1)
    time.sleep(0.2)  # Wait for the key to expire
    with pytest.raises(KeyError):
        value = d['key2']
    
    # Check that expired key is also removed from expiry dict
    assert 'key2' not in d.expiry


def test_delitem(tmp_path):
    d = ExpiringDict()
    d['key1'] = 'value1'
    d.set_with_ttl('key2', 'value2', ttl=10)
    
    # Test deleting a key
    del d['key1']
    assert 'key1' not in d
    
    # Test deleting a key with expiry
    del d['key2']
    assert 'key2' not in d
    assert 'key2' not in d.expiry
    
    # Test that _save is called when filename is set
    with patch('talkpipe.util.collections.ExpiringDict._save') as mock_save:
        temp_filename = tmp_path / "test_file"
        d = ExpiringDict(filename=temp_filename)
        d['key1'] = 'value1'
        mock_save.reset_mock()
        del d['key1']
        mock_save.assert_called_once()


def test_clean_expired(tmp_path):
    d = ExpiringDict()
    
    # Add some items with different expiry times
    d.set_with_ttl('expires_soon', 'value1', ttl=0.1)
    d.set_with_ttl('expires_later', 'value2', ttl=10)
    d['no_expiry'] = 'value3'
    
    # Wait for the first key to expire
    time.sleep(0.2)
    
    # Clean expired keys
    d._clean_expired()
    
    # Check that the expired key is gone
    assert 'expires_soon' not in d
    assert 'expires_soon' not in d.expiry
    
    # Check that other keys are still there
    assert 'expires_later' in d
    assert 'no_expiry' in d
    
    # Test that _save is called when filename is set
    with patch('talkpipe.util.collections.ExpiringDict._save') as mock_save:
        temp_filename = tmp_path / "test_file"
        d = ExpiringDict(filename=temp_filename)
        d.set_with_ttl('expires_soon', 'value1', ttl=0.1)
        time.sleep(0.2)
        mock_save.reset_mock()
        d._clean_expired()
        mock_save.assert_called_once()


def test_dict_methods():
    d = ExpiringDict(default_ttl=10)
    
    # Test clear
    d['key1'] = 'value1'
    d.clear()
    assert len(d) == 0
    assert len(d.expiry) == 0
    
    # Test update
    d.update({'key1': 'value1', 'key2': 'value2'})
    assert len(d) == 2
    
    # Test pop
    value = d.pop('key1')
    assert value == 'value1'
    assert 'key1' not in d
    assert 'key1' not in d.expiry
    
    # Test popitem
    key, value = d.popitem()
    assert key == 'key2'
    assert value == 'value2'
    assert len(d) == 0
    
    # Test iteration methods
    d.set_with_ttl('key1', 'value1', ttl=10)
    d.set_with_ttl('key2', 'value2', ttl=10)
    
    assert set(d.keys()) == {'key1', 'key2'}
    assert set(d.values()) == {'value1', 'value2'}
    assert set(d.items()) == {('key1', 'value1'), ('key2', 'value2')}
    
    # Test __len__ and __contains__
    assert len(d) == 2
    assert 'key1' in d
    assert 'key3' not in d


def test_persistence(tmp_path):
    # Test saving to file
    temp_filename = tmp_path / "test_shelve_file"
    d1 = ExpiringDict(filename=temp_filename, default_ttl=10)
    d1['key1'] = 'value1'
    d1.set_with_ttl('key2', 'value2', ttl=10)
    
    # Create a new dict that loads from the same file
    d2 = ExpiringDict(filename=temp_filename)
    assert len(d2) == 2
    assert d2['key1'] == 'value1'
    assert d2['key2'] == 'value2'
    
    # Test that changes in the new dict are saved
    d2['key3'] = 'value3'
    
    # Create another dict to verify the changes were saved
    d3 = ExpiringDict(filename=temp_filename)
    assert len(d3) == 3
    assert d3['key3'] == 'value3'
    
    # Test loading from a non-existent file
    nonexistent_file = tmp_path / 'test_shelve_file_nonexistent'
    d4 = ExpiringDict(filename=nonexistent_file)
    assert len(d4) == 0


def test_expiry_on_load(tmp_path):
    temp_filename = tmp_path / "test_shelve_file"
    # Create a dict with short-lived entries
    d1 = ExpiringDict(filename=temp_filename)
    d1.set_with_ttl('expires_soon', 'value1', ttl=0.1)
    d1.set_with_ttl('expires_later', 'value2', ttl=10)
    
    # Wait for the first key to expire
    time.sleep(0.2)
    
    # Load the dict again - it should clean expired keys
    d2 = ExpiringDict(filename=temp_filename)
    assert 'expires_soon' not in d2
    assert 'expires_later' in d2


def test_save_load_functionality(tmp_path):
    temp_filename = tmp_path / "test_shelve_file"
    """Test that _save and _load methods work correctly"""
    d = ExpiringDict(filename=temp_filename)
    
    # Add some data
    d['key1'] = 'value1'
    d.set_with_ttl('key2', 'value2', ttl=100)
    
    # Create a new instance to test loading
    d2 = ExpiringDict(filename=temp_filename)
    assert 'key1' in d2
    assert 'key2' in d2
    assert d2['key1'] == 'value1'
    assert d2['key2'] == 'value2'


def test_exception_handling():
    """Test that the class handles exceptions gracefully"""
    # Test with invalid filename
    with patch('shelve.open', side_effect=Exception("Simulated error")):
        d = ExpiringDict(filename="invalid_file")
        assert len(d) == 0
        assert len(d.expiry) == 0


def test_update_with_ttl():
    """Test update method with TTL preservation"""
    d = ExpiringDict()
    d.set_with_ttl('key1', 'value1', ttl=10)
    
    # Update without changing TTL
    start_time = time.time()
    d['key1'] = 'updated_value1'
    
    # The key should still have an expiry
    assert 'key1' in d.expiry
    
    # Now update other keys and check they don't affect existing TTLs
    d.update({'key2': 'value2', 'key3': 'value3'})
    assert 'key2' not in d.expiry
    assert 'key3' not in d.expiry
    assert 'key1' in d.expiry


def test_iteration_methods_with_expired_keys():
    """Test that keys(), values(), and items() correctly handle expired keys"""
    d = ExpiringDict()
    
    # Add keys with different expiry times
    d.set_with_ttl('expires_soon', 'value1', ttl=0.1)
    d.set_with_ttl('expires_later', 'value2', ttl=10)
    d['no_expiry'] = 'value3'
    
    # Wait for the first key to expire
    time.sleep(0.2)
    
    # Test that keys() correctly removes expired keys
    keys = list(d.keys())
    assert 'expires_soon' not in keys
    assert 'expires_later' in keys
    assert 'no_expiry' in keys
    
    # Test that values() correctly removes expired keys
    values = list(d.values())
    assert 'value1' not in values
    assert 'value2' in values
    assert 'value3' in values
    
    # Test that items() correctly removes expired keys
    items = dict(d.items())
    assert 'expires_soon' not in items
    assert 'expires_later' in items
    assert 'no_expiry' in items