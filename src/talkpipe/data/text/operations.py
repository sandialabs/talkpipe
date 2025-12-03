from talkpipe.util.data_manipulation import extract_property


from typing import Any, Iterator, Tuple, Union


def shingle_generator(text_chunks: Iterator[Any], string_field: str, key_field: str, shingle_size: int, overlap: int, delimiter=' ', size_mode: str = 'count', include_paragraph_numbers: bool = False) -> Union[Iterator[Tuple[Any, str]], Iterator[Tuple[Any, str, int, int]]]:
    """Generates shingles from text chunks.

    Args:
        text_chunks: Iterator of items to process
        string_field: Field to extract text from (or None to use item directly)
        key_field: Field to use for grouping/key detection
        shingle_size: Size threshold - either number of chunks (count mode) or minimum character length (length mode)
        overlap: Number of chunks to keep for overlap between shingles
        delimiter: String to join chunks with
        size_mode: Either 'count' (count chunks) or 'length' (measure character length)
        include_paragraph_numbers: If True, yields 4-tuples (item, text, first_para, last_para) instead of 2-tuples (item, text)
    """
    shingles = []
    current_key = None
    last_item = None
    paragraph_numbers = []
    paragraph_counter = 0
    has_yielded_for_key = False

    def is_shingle_complete():
        """Check if current shingle meets size threshold."""
        if size_mode == 'length':
            return len(delimiter.join(shingles)) >= shingle_size
        else:  # count mode
            return len(shingles) == shingle_size

    def yield_shingle():
        """Yield current shingle with appropriate format."""
        yield_item = last_item.copy() if isinstance(last_item, dict) else last_item
        shingle_text = delimiter.join(shingles)
        if include_paragraph_numbers:
            return yield_item, shingle_text, paragraph_numbers[0], paragraph_numbers[-1]
        else:
            return yield_item, shingle_text

    for item in text_chunks:
        text = extract_property(item, string_field) if string_field else item

        # Check for key change
        if key_field:
            item_key = extract_property(item, key_field)
            if current_key is not None and item_key != current_key:
                # Yield remaining shingle before resetting for new key
                # Yield if complete, or if incomplete but we never yielded anything for this key,
                # or if overlap=0 (no overlap means boundaries should be yielded),
                # or (in count mode only) if we have new data beyond the overlap from the last shingle
                if shingles and (is_shingle_complete() or not has_yielded_for_key or overlap == 0 or (size_mode == 'count' and len(shingles) > overlap)):
                    yield yield_shingle()
                shingles = []
                paragraph_numbers = []
                paragraph_counter = 0
                has_yielded_for_key = False
            current_key = item_key

        last_item = item
        shingles.append(text)
        paragraph_numbers.append(paragraph_counter)
        paragraph_counter += 1

        # Yield complete shingle and keep overlap
        if is_shingle_complete():
            yield yield_shingle()
            has_yielded_for_key = True
            shingles = shingles[-overlap:] if overlap > 0 else []
            paragraph_numbers = paragraph_numbers[-overlap:] if overlap > 0 else []

    # Yield final shingle at end of stream
    # Yield if complete, or if incomplete but we never yielded anything for this key,
    # or if overlap=0 (no overlap means boundaries should be yielded),
    # or (in count mode only) if we have new data beyond the overlap from the last shingle
    if shingles and (is_shingle_complete() or not has_yielded_for_key or overlap == 0 or (size_mode == 'count' and len(shingles) > overlap)):
        yield yield_shingle()