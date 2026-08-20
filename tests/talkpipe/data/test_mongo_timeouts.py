"""MongoDB segments must bound server selection and release the client on
every exit path. These tests run offline against a recording double."""

from typing import ClassVar

import pytest

from talkpipe.data import mongo
from talkpipe.util.constants import DEFAULT_MONGO_TIMEOUT


class _RecordingClient:
    created: ClassVar[list] = []

    def __init__(self, connection_string, **kwargs):
        self.connection_string = connection_string
        self.kwargs = kwargs
        self.closed = False
        self.fail_on_insert = False
        _RecordingClient.created.append(self)

    def __getitem__(self, _name):
        return self

    def create_index(self, *_a, **_k):
        pass

    def insert_one(self, doc):
        if self.fail_on_insert:
            raise RuntimeError("boom")

        class R:
            inserted_id = "id"

        return R()

    def find(self, **_k):
        raise RuntimeError("cursor exploded")

    def close(self):
        self.closed = True


@pytest.fixture
def recording_client(monkeypatch):
    _RecordingClient.created.clear()
    monkeypatch.setattr(mongo, "MongoClient", _RecordingClient)
    return _RecordingClient


def test_mongo_insert_passes_default_timeout(recording_client):
    seg = mongo.MongoInsert(
        connection_string="mongodb://x", database="d", collection="c"
    )
    list(seg(["a"]))
    client = recording_client.created[0]
    assert client.kwargs["serverSelectionTimeoutMS"] == int(
        DEFAULT_MONGO_TIMEOUT * 1000
    )
    assert client.kwargs["connectTimeoutMS"] == int(DEFAULT_MONGO_TIMEOUT * 1000)


def test_mongo_insert_passes_explicit_timeout(recording_client):
    seg = mongo.MongoInsert(
        connection_string="mongodb://x", database="d", collection="c", timeout=2.5
    )
    list(seg(["a"]))
    assert recording_client.created[0].kwargs["serverSelectionTimeoutMS"] == 2500


def test_mongo_insert_closes_client_when_consumer_stops_early(recording_client):
    seg = mongo.MongoInsert(
        connection_string="mongodb://x", database="d", collection="c"
    )
    gen = seg(["a", "b", "c"])
    next(gen)
    gen.close()
    assert recording_client.created[0].closed


def test_mongo_search_passes_timeout_and_closes_on_error(recording_client):
    seg = mongo.MongoSearch(
        connection_string="mongodb://x", database="d", collection="c", timeout=1
    )
    with pytest.raises(RuntimeError):
        list(seg(['{"a": 1}']))
    client = recording_client.created[0]
    assert client.kwargs["serverSelectionTimeoutMS"] == 1000
    assert client.closed
