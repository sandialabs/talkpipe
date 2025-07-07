from typing import List, Any
import os
import uuid
from whoosh import index
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser
from talkpipe.search.fulltext import AbstractFullTextIndex, SearchResult
from talkpipe.util.data_manipulation import extract_property
from talkpipe.pipe import segment
from talkpipe.chatterlang import register_segment
from talkpipe.util.data_manipulation import toDict

class WhooshFullTextIndex(AbstractFullTextIndex):
    def __init__(self, index_path: str, fields: list[str]):
        self.index_path = index_path
        self.fields = fields
        self.schema = Schema(
            doc_id=ID(stored=True, unique=True),
            **{field: TEXT(stored=True) for field in fields}
        )
        if not os.path.exists(index_path):
            os.makedirs(index_path)
        if index.exists_in(index_path):
            self.ix = index.open_dir(index_path)
            # Check schema fields
            ix_fields = set(self.ix.schema.names())
            expected_fields = set(['doc_id'] + fields)
            if ix_fields != expected_fields:
                raise ValueError(f"Index schema fields {ix_fields} do not match expected {expected_fields}")
        else:
            self.ix = index.create_in(index_path, self.schema)
        self.writer = None

    def __enter__(self):
        self.writer = self.ix.writer()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.writer is not None:
            self.writer.commit()
            self.writer = None
        self.ix.close()

    def add_document(self, document: dict[str, Any]) -> None:
        doc_id = str(document.get("doc_id") or uuid.uuid4())
        doc_fields = {field: str(document.get(field, "")) for field in self.fields}
        if self.writer is not None:
            self.writer.update_document(doc_id=doc_id, **doc_fields)
        else:
            with self.ix.writer() as writer:
                writer.update_document(doc_id=doc_id, **doc_fields)

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        with self.ix.searcher() as searcher:
            parser = MultifieldParser(self.fields, schema=self.ix.schema)
            q = parser.parse(query)
            results = searcher.search(q, limit=limit)
            search_results = []
            for hit in results:
                metadata = {field: hit.get(field) for field in self.fields}
                search_results.append(
                    SearchResult(
                        doc_id=hit['doc_id'],
                        score=hit.score,
                        snippet=None,
                        metadata=metadata
                    )
                )
            return search_results

    def clear(self) -> None:
        if self.writer is not None:
            self.writer.cancel()
            self.writer = None
        self.ix.close()
        for fname in os.listdir(self.index_path):
            fpath = os.path.join(self.index_path, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)
        self.ix = index.create_in(self.index_path, self.schema)

@register_segment("indexWhoosh")
@segment
def indexWhoosh(items, fields: list[str], index_path: str) -> None:
    """Index documents using Whoosh full-text indexing.

    Args:
        items (list[dict]): List of documents to index.
        fields (list[str]): List of fields to index.
        index_path (str): Path to the Whoosh index directory.
    """
    with WhooshFullTextIndex(index_path, fields) as idx:
        for item in items:
            d = toDict(item, ','.join(fields), fail_on_missing=False)
            d_str = {k:str(v) for k, v in d.items()}
            idx.add_document(d_str)