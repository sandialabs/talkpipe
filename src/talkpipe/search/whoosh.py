from typing import List, Any
import os
import uuid
from whoosh import index
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser
from talkpipe.pipe import segment
from talkpipe.chatterlang import register_segment
from talkpipe.util.data_manipulation import toDict
from talkpipe.util.config import parse_key_value_str
from .abstract import AbstractFullTextIndex, SearchResult

class WhooshFullTextIndex(AbstractFullTextIndex):
    def __init__(self, index_path: str, fields: list[str] = None):
        self.index_path = index_path
        self.fields = fields
        if not os.path.exists(index_path):
            os.makedirs(index_path)
        if index.exists_in(index_path):
            self.ix = index.open_dir(index_path)
            self.schema = self.ix.schema
            ix_fields = set(self.ix.schema.names())
            expected_fields = set(self.ix.schema.names())
            if fields is not None:
                expected_fields = set(['doc_id'] + fields)
                if ix_fields != expected_fields:
                    raise ValueError(f"Index schema fields {ix_fields} do not match expected {expected_fields}")
                self.fields = fields
            else:
                # Use fields from existing index if not provided
                self.fields = [f for f in self.ix.schema.names() if f != 'doc_id']
        else:
            if fields is None:
                raise ValueError("Fields must be provided when creating a new index.")
            self.schema = Schema(
                doc_id=ID(stored=True, unique=True),
                **{field: TEXT(stored=True) for field in fields}
            )
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

    def search(self, query: str, limit: int = 100) -> List[SearchResult]:
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
@segment()
def indexWhoosh(items, index_path: str, field_list: list[str] = ["_:content"], yield_doc=False):
    """Index documents using Whoosh full-text indexing.

    Args:
        fields (list[str]): List of fields to index.
        index_path (str): Path to the Whoosh index directory.
        yield_doc (bool): If True, yield each indexed document.  Otherwise yield the original
        item.
    """
    field_list_dict = parse_key_value_str(field_list)
    with WhooshFullTextIndex(index_path, list(field_list_dict.values())) as idx:
        for item in items:
            d = toDict(item, field_list, fail_on_missing=False)
            d['doc_id'] = str(d.get('doc_id', uuid.uuid4()))
            d_str = {k:str(v) for k, v in d.items()}
            idx.add_document(d_str)
            yield d if yield_doc else item

@register_segment("searchWhoosh")
@segment()
def searchWhoosh(queries, index_path: str, limit: int = 100, all_results_at_once: bool = False):
    """Search documents using Whoosh full-text indexing.

    Args:
        index_path (str): Path to the Whoosh index directory.
        limit (int): Maximum number of results to return for each query.  Defaults to 100.
        all_results_at_once (bool): If True, yield all results at once. Otherwise, yield one result at a time.
    """
    with WhooshFullTextIndex(index_path) as idx:
        for query in queries:
            results = idx.search(query, limit=limit)
            if all_results_at_once:
                yield results
            else:
                for result in results:
                    yield result