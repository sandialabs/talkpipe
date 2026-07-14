import base64

from talkpipe.data.text.cleaning import strip_base64_blobs, stripBase64


def test_strip_base64_blobs_removes_data_uri():
    payload = base64.b64encode(b"fake image bytes").decode()
    text = f"Receipt for Ole Miss payment. ![img](data:image/png;base64,{payload}) Total: $250."
    cleaned = strip_base64_blobs(text)
    assert payload not in cleaned
    assert "data:image/png" not in cleaned
    assert "Receipt for Ole Miss payment." in cleaned
    assert "Total: $250." in cleaned


def test_strip_base64_blobs_removes_long_bare_run():
    blob = base64.b64encode(b"x" * 600).decode()
    text = f"Before the blob. {blob} After the blob."
    cleaned = strip_base64_blobs(text)
    assert blob not in cleaned
    assert "Before the blob." in cleaned
    assert "After the blob." in cleaned


def test_strip_base64_blobs_removes_multiline_wrapped_payload():
    # MIME/PEM-style base64 wrapped at 64 or 76 characters per line
    raw = base64.b64encode(b"binary attachment content, long enough to wrap" * 10).decode()
    wrapped = "\n".join(raw[i:i + 64] for i in range(0, len(raw), 64))
    text = f"Attached certificate:\n{wrapped}\nRegards, Alice"
    cleaned = strip_base64_blobs(text)
    assert raw[:64] not in cleaned
    assert "Attached certificate:" in cleaned
    assert "Regards, Alice" in cleaned


def test_strip_base64_blobs_preserves_normal_text():
    text = (
        "Supercalifragilisticexpialidocious words, URLs like https://example.com/some/path, "
        "hex hashes like 72a2a15650abc, and identifiers_like_this stay untouched."
    )
    assert strip_base64_blobs(text) == text


def test_strip_base64_blobs_preserves_long_non_base64_runs():
    repeated = "a" * 300
    dna = "ACGTTGCAACGTTGCA" * 8  # long, but no lowercase or digits
    hexdigest = "9f2c7e1a8b4d" * 8  # long, but no uppercase
    text = f"{repeated} {dna} {hexdigest}"
    assert strip_base64_blobs(text) == text


def test_strip_base64_blobs_min_run_configurable():
    run = "A1b2C3d4" * 4  # 32 chars, below default threshold
    text = f"token {run} end"
    assert run in strip_base64_blobs(text)
    assert run not in strip_base64_blobs(text, min_run=32)


def test_stripBase64_segment_sets_field():
    blob = base64.b64encode(b"y" * 300).decode()
    items = [{"content": f"Real text. {blob}", "id": "doc1"}]
    seg = stripBase64(field="content", set_as="content").as_function()
    result = list(seg(items))
    assert len(result) == 1
    assert blob not in result[0]["content"]
    assert "Real text." in result[0]["content"]
    assert result[0]["id"] == "doc1"
