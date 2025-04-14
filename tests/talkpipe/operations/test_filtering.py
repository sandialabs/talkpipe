from talkpipe.operations import filtering

def test_bloomfilter():
    # Create a Bloom Filter expecting to store 100 items with a 1% false positive probability.
    bf = filtering.BloomFilter(capacity=100, error_rate=0.01)

    # Add some items to the Bloom Filter.
    words_to_add = ["apple", "banana", "cherry"]
    words_to_not_add = ["durian", "elderberry"]
    for word in words_to_add:
        bf.add(word)
        print(f"Added {word} to the Bloom Filter.")

    assert all(word in bf for word in words_to_add)
    assert all(word not in bf for word in words_to_not_add)

    bf = filtering.BloomFilter(capacity=1000, error_rate=0.01)
    for i in range(500):
        bf.add(i)
    assert all(i in bf for i in range(500))

    # Test for false positives
    false_positives = 0
    test_range = range(500, 1500)  # Range of elements not inserted
    for i in test_range:
        if i in bf:
            false_positives += 1

    # Calculate the false positive rate
    false_positive_rate = false_positives / len(test_range)
    # error if the false positive rate is greater than 3%.  This can happen
    # in principle, but should be very rare.
    assert false_positive_rate < 0.03 

def test_bloomfilter_segment():
    bfs = filtering.distinctBloomFilter(capacity=100, error_rate=0.01)
    bfs = bfs.asFunction(single_in=False, single_out=False)
    ans = list(bfs(["apple", "banana", "cherry", "apple", "banana", "cherry", "durian", "elderberry"]))
    assert ans == ["apple", "banana", "cherry", "durian", "elderberry"]

    bfs = filtering.distinctBloomFilter(capacity=100, error_rate=0.01, field_list="x")
    bfs = bfs.asFunction(single_in=False, single_out=False)
    ans = list(bfs([{"x": "apple"}, {"x": "banana"}, {"x": "cherry"}, {"x": "apple"}, {"x": "banana"}, {"x": "cherry"}, {"x": "durian"}, {"x": "elderberry", "y": "apple"}, {"x": "elderberry", "y": "banana"}]))
    assert ans == [{"x": "apple"}, {"x": "banana"}, {"x": "cherry"}, {"x": "durian"}, {"x": "elderberry", "y": "apple"}]