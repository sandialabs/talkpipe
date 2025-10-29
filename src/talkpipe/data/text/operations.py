from talkpipe.util.data_manipulation import extract_property


from typing import Any, Iterator, Tuple


def shingle_generator(text_chunks: Iterator[Any], string_field: str, key_field: str, shingle_size: int, overlap: int, delimiter=' ', size_mode: str = 'count') -> Iterator[Tuple[Any, str]]:
    """Generates shingles from text chunks.

    Args:
        text_chunks: Iterator of items to process
        string_field: Field to extract text from (or None to use item directly)
        key_field: Field to use for grouping/key detection
        shingle_size: Size threshold - either number of chunks (count mode) or minimum character length (length mode)
        overlap: Number of chunks to keep for overlap between shingles
        delimiter: String to join chunks with
        size_mode: Either 'count' (count chunks) or 'length' (measure character length)
    """
    shingles = []
    current_key = None
    last_item = None

    def is_shingle_complete():
        """Check if current shingle meets size threshold."""
        if size_mode == 'length':
            return len(delimiter.join(shingles)) >= shingle_size
        else:  # count mode
            return len(shingles) == shingle_size

    for item in text_chunks:
        text = extract_property(item, string_field) if string_field else item
        if key_field:
            item_key = extract_property(item, key_field) if key_field else None
            if current_key is not None and item_key != current_key:
                if shingles and (is_shingle_complete() or overlap == 0):
                    yield_item = last_item.copy() if isinstance(last_item, dict) else last_item
                    yield yield_item, delimiter.join(shingles)
                shingles = []
            current_key = item_key

        last_item = item
        shingles.append(text)

        if is_shingle_complete():
            yield_item = last_item.copy() if isinstance(last_item, dict) else last_item
            yield yield_item, delimiter.join(shingles)
            shingles = shingles[-overlap:] if overlap > 0 else []

    if shingles and (is_shingle_complete() or overlap == 0):
        yield_item = last_item.copy() if isinstance(last_item, dict) else last_item
        yield yield_item, delimiter.join(shingles)