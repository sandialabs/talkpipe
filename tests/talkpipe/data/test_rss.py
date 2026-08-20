import pickle

import feedparser

from talkpipe.chatterlang.compiler import compile
from talkpipe.data import rss


def test_rss(monkeypatch):
    with open("tests/talkpipe/data/sample_feed.pkl", "rb") as f:
        sample_rss = pickle.load(f)

    monkeypatch.setattr(feedparser, "parse", lambda x: sample_rss)

    ans = list(
        rss.rss_monitor(
            "http://example.com/feed", db_path=":memory:", poll_interval_minutes=-1
        )
    )
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
    f = compiled.as_function()
    ans = list(f())

    for item in ans:
        assert isinstance(item, dict)
        assert "title" in item
        assert "link" in item
        assert "published" in item
        assert "summary" in item
        assert "author" in item
    assert len(ans) == 8


def test_rss_closes_database_when_consumer_stops_early(monkeypatch, tmp_path):
    """The SQLite connection must be released even if the caller abandons the
    generator (e.g. via firstN); otherwise the file handle leaks for the
    process lifetime."""
    import sqlite3

    with open("tests/talkpipe/data/sample_feed.pkl", "rb") as f:
        sample_rss = pickle.load(f)
    monkeypatch.setattr(feedparser, "parse", lambda x: sample_rss)

    opened = []
    real_connect = sqlite3.connect

    class Tracking:
        def __init__(self, conn):
            self._conn = conn
            self.closed = False

        def close(self):
            self.closed = True
            self._conn.close()

        def __getattr__(self, name):
            return getattr(self._conn, name)

    def tracking_connect(*a, **k):
        conn = Tracking(real_connect(*a, **k))
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    gen = rss.rss_monitor("http://example.com/feed", db_path=str(tmp_path / "f.db"))
    next(gen)
    gen.close()
    assert opened
    assert opened[0].closed
