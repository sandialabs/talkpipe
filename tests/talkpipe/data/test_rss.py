import os
import pickle
import feedparser
from talkpipe.data import rss
from talkpipe.chatterlang.compiler import compile

def test_rss(monkeypatch):
    with open("tests/talkpipe/data/sample_feed.pkl", "rb") as f:
        sample_rss = pickle.load(f)

    monkeypatch.setattr(feedparser, "parse", lambda x: sample_rss)

    ans = list(rss.rss_monitor("http://example.com/feed", db_path=":memory:", poll_interval_minutes=-1))
    for item in ans:
        assert isinstance(item, dict)
        assert "title" in item
        assert "link" in item
        assert "published" in item
        assert "summary" in item
        assert "author" in item
    assert len(ans) == 8

def test_rss_segment(monkeypatch):
    with open("tests/talkpipe/data/sample_feed.pkl", "rb") as f:
        sample_rss = pickle.load(f)

    monkeypatch.setattr(feedparser, "parse", lambda x: sample_rss)

    code = """
    INPUT FROM rss[url="http://example.com/feed", db_path=":memory:", poll_interval_minutes=-1]
    """
    compiled = compile(code)
    f = compiled.asFunction()
    ans = list(f())

    for item in ans:
        assert isinstance(item, dict)
        assert "title" in item
        assert "link" in item
        assert "published" in item
        assert "summary" in item
        assert "author" in item
    assert len(ans) == 8
