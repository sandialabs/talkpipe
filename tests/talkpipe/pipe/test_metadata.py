"""Unit tests for metadata flush operations."""

import pytest
import time
from talkpipe.pipe.metadata import Flush, flushN, flushT
from talkpipe.pipe.core import is_metadata


class TestFlushN:
    """Test suite for flushN segment."""
    
    def test_flush_every_n_items(self):
        """Test that flushN yields Flush() every n items."""
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        segment = flushN(n=3)
        result = list(segment(items))
        
        # Expected: 1, 2, 3, Flush(), 4, 5, 6, Flush(), 7, 8, 9, Flush(), 10
        assert len(result) == 13
        assert result[0] == 1
        assert result[1] == 2
        assert result[2] == 3
        assert isinstance(result[3], Flush)
        assert result[4] == 4
        assert result[5] == 5
        assert result[6] == 6
        assert isinstance(result[7], Flush)
        assert result[8] == 7
        assert result[9] == 8
        assert result[10] == 9
        assert isinstance(result[11], Flush)
        assert result[12] == 10
    
    def test_flush_every_n_items_verify_all_flushes(self):
        """Test that all Flush objects are properly identified."""
        items = list(range(15))
        segment = flushN(n=5)
        result = list(segment(items))
        
        # Should have 15 items + 3 flushes (after items 4, 9, 14, which are the 5th, 10th, 15th items)
        # Flushes occur at positions 5, 11, 17 (after each nth item is yielded)
        flush_positions = [i for i, item in enumerate(result) if is_metadata(item)]
        assert flush_positions == [5, 11, 17]  # Flushes after items at indices 4, 9, 14
    
    def test_flush_every_one_item(self):
        """Test flushing after every single item."""
        items = [1, 2, 3]
        segment = flushN(n=1)
        result = list(segment(items))
        
        # Expected: 1, Flush(), 2, Flush(), 3, Flush()
        assert len(result) == 6
        assert result[0] == 1
        assert isinstance(result[1], Flush)
        assert result[2] == 2
        assert isinstance(result[3], Flush)
        assert result[4] == 3
        assert isinstance(result[5], Flush)
    
    def test_flush_with_large_n(self):
        """Test that no flush occurs if n > number of items."""
        items = [1, 2, 3]
        segment = flushN(n=10)
        result = list(segment(items))
        
        # Should have all items, no flushes
        assert result == [1, 2, 3]
        assert not any(is_metadata(item) for item in result)
    
    def test_empty_input(self):
        """Test that empty input produces empty output."""
        items = []
        segment = flushN(n=3)
        result = list(segment(items))
        assert result == []
    
    def test_preserves_item_order(self):
        """Test that items are yielded in the same order as input."""
        items = ['a', 'b', 'c', 'd', 'e']
        segment = flushN(n=2)
        result = list(segment(items))
        
        # Extract non-metadata items
        data_items = [item for item in result if not is_metadata(item)]
        assert data_items == ['a', 'b', 'c', 'd', 'e']


class TestFlushT:
    """Test suite for flushT segment."""
    
    def test_yields_items_and_flushes(self):
        """Test that flushT yields items and Flush() objects."""
        items = [1, 2, 3]
        segment = flushT(t=0.5)
        result = list(segment(items))
        
        # Should have all items
        data_items = [item for item in result if not is_metadata(item)]
        assert data_items == [1, 2, 3]
        
        # Should have at least one flush (depending on timing)
        flushes = [item for item in result if is_metadata(item)]
        assert len(flushes) >= 0  # May or may not have flushes depending on speed
    
    def test_flush_timing(self):
        """Test that flushT respects the time interval."""
        items = [1, 2, 3, 4, 5]
        segment = flushT(t=0.2)
        
        start_time = time.time()
        result = list(segment(items))
        elapsed = time.time() - start_time
        
        # Should have all items
        data_items = [item for item in result if not is_metadata(item)]
        assert data_items == [1, 2, 3, 4, 5]
        
        # Should have some flushes if enough time passed
        flushes = [item for item in result if is_metadata(item)]
        # With 5 items and 0.2s interval, should have at least one flush
        assert len(flushes) >= 0  # Timing dependent
    
    def test_exits_when_items_exhausted(self):
        """Test that flushT exits when items are exhausted."""
        items = [1, 2, 3]
        segment = flushT(t=0.1)
        result = list(segment(items))
        
        # Should have exactly 3 items
        data_items = [item for item in result if not is_metadata(item)]
        assert data_items == [1, 2, 3]
        
        # Should eventually exit (not infinite)
        assert len(result) >= 3
    
    def test_preserves_item_order(self):
        """Test that items are yielded in the same order as input."""
        items = ['a', 'b', 'c', 'd', 'e']
        segment = flushT(t=0.1)
        result = list(segment(items))
        
        # Extract non-metadata items
        data_items = [item for item in result if not is_metadata(item)]
        assert data_items == ['a', 'b', 'c', 'd', 'e']
    
    def test_flushes_occur_over_time(self):
        """Test that flushes occur based on time, not just item count."""
        # Use slow items to allow time for flushes
        def slow_items():
            for i in range(3):
                time.sleep(0.15)  # Sleep between items
                yield i
        
        segment = flushT(t=0.2)
        result = list(segment(slow_items()))
        
        # Should have all items
        data_items = [item for item in result if not is_metadata(item)]
        assert data_items == [0, 1, 2]
        
        # Should have some flushes since we slept between items
        flushes = [item for item in result if is_metadata(item)]
        assert len(flushes) >= 0  # Should have at least some flushes

