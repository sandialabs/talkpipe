import pytest
from talkpipe.data.extraction import FileExtractor, readtxt, readdocx

def test_readdocx():
    rd = readdocx()
    text = list(rd(["tests/talkpipe/data/test.docx"]))[0]
    assert text.startswith("This is a sample document.")

def test_readtxt(tmp_path):
    with open(tmp_path / "test.txt", "w") as file:
        file.write("Hello World")   
    assert next(readtxt()([tmp_path / "test.txt"])) == "Hello World"

    with open(tmp_path / "test.md", "w") as file:
        file.write("Hello Markdown")
    assert next(readtxt()([tmp_path / "test.md"])) == "Hello Markdown"

def test_FileExtractor(tmp_path):
    fe = FileExtractor()

    with open(tmp_path / "test.txt", "w") as file:
        file.write("Hello World")   
    assert next(fe([tmp_path / "test.txt"])) == "Hello World"

    with open(tmp_path / "test.md", "w") as file:
        file.write("Hello Markdown")
    assert next(fe([tmp_path / "test.md"])) == "Hello Markdown"

    with open(tmp_path / "test.doc", "w") as file:
        file.write("Hello Word")
    with pytest.raises(Exception):
        next(fe([tmp_path / "test.doc"]))

    