import logging
import math
import hashlib

from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.data_manipulation import extract_property

logger = logging.getLogger(__name__)

class BloomFilter:
    def __init__(self, capacity, error_rate):
        """
        Initialize the Bloom Filter.

        :param capacity: Expected number of items to be stored.
        :param error_rate: Desired false positive probability (e.g., 0.01 for 1%).
        """
        self.capacity = capacity
        self.error_rate = error_rate

        # Calculate the size of the bit array (m) using:
        # m = - (n * ln(p)) / (ln2)^2
        self.size = math.ceil(-(capacity * math.log(error_rate)) / (math.log(2) ** 2))
        
        # Calculate the optimal number of hash functions (k) using:
        # k = (m/n) * ln2
        self.hash_count = math.ceil((self.size / capacity) * math.log(2))
        
        # Initialize the bit array with all bits set to False (0)
        self.bit_array = [False] * self.size

    def _hashes(self, item):
        """
        Generate hash values for the given item using double hashing.

        :param item: The item to hash.
        :yield: A sequence of positions in the bit array.
        """
        # Convert the item to bytes (if it's not already) so it can be hashed.
        item_bytes = str(item).encode('utf-8')
        
        # First hash using MD5
        hash1 = int(hashlib.md5(item_bytes).hexdigest(), 16)
        # Second hash using SHA-1
        hash2 = int(hashlib.sha1(item_bytes).hexdigest(), 16)
        
        # Generate hash values using double hashing:
        # For each i, compute: (hash1 + i * hash2) mod size
        for i in range(self.hash_count):
            yield (hash1 + i * hash2) % self.size

    def add(self, item):
        """
        Add an item to the Bloom Filter.

        :param item: The item to add.
        """
        for index in self._hashes(item):
            self.bit_array[index] = True

    def __contains__(self, item):
        """
        Check if an item is possibly in the Bloom Filter.

        :param item: The item to check.
        :return: True if the item might be in the filter, False if the item is definitely not in the filter.
        """
        return all(self.bit_array[index] for index in self._hashes(item))

@registry.register_segment("distinctBloomFilter")
@core.segment()
def distinctBloomFilter(items, capacity, error_rate, field_list="_"):
    """
    Filter items using a Bloom Filter to yield only distinct elements based on specified fields.

    A Bloom Filter is a space-efficient probabilistic data structure used to test whether 
    an element is a member of a set. False positive matches are possible, but false 
    negatives are not.

    Args:
        items (iterable): Input items to filter.
        capacity (int): Expected number of items to be added to the Bloom Filter.
        error_rate (float): Acceptable false positive probability (between 0 and 1).
        field_list (str, optional): Dot-separated string of nested fields to use for 
            distinctness check. Defaults to "_" which uses the entire item.

    Yields:
        item: Items that have not been seen before according to the Bloom Filter.

    Example:
        >>> items = [{"id": 1, "name": "John"}, {"id": 2, "name": "John"}]
        >>> list(distinctBloomFilter(items, 1000, 0.01, "name"))
        [{'id': 1, 'name': 'John'}]  # Only first item with name "John" is yielded

    Note:
        Due to the probabilistic nature of Bloom Filters, there is a small chance
        of false positives (items incorrectly identified as duplicates) based on
        the specified error_rate.
    """
    logger.debug(f"Creating a Bloom Filter with capacity={capacity} and error_rate={error_rate}.")
    bf = BloomFilter(capacity=capacity, error_rate=error_rate)
    for item in items:
        extracted = extract_property(item, field_list)
        if extracted not in bf:
            logger.debug(f"Adding {str(item)} ({str(extracted)}) to the Bloom Filter and yielding it.")
            bf.add(extracted)
            yield item
        else:
            logger.debug(f"{str(item)} ({str(extracted)}) is already in the Bloom Filter; skipping.")

