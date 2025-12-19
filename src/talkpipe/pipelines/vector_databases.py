from typing import Optional, Annotated
from talkpipe import AbstractSegment, register_segment
from talkpipe.search.lancedb import add_to_lancedb, search_lancedb
from talkpipe.llm.embedding import LLMEmbed


@register_segment("makeVectorDatabase")
class MakeVectorDatabaseSegment(AbstractSegment):
    """Segment to create a vector database in LanceDB.

    This segment expects dictionary inputs representing documents.
    It embeds the specified field and stores the documents with their embeddings in LanceDB.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(self,
                 embedding_field: Annotated[str, "Field to use for embeddings"],
                 embedding_model: Annotated[str, "Embedding model to use"],
                 embedding_source: Annotated[str, "Source of text to embed"],
                 path: Annotated[str, "Path to LanceDB database. Supports file paths or 'tmp://name'"],
                 table_name: Annotated[str, "Name of the table in the database"] = "docs",
                 doc_id_field: Annotated[Optional[str], "Field containing document ID"] = None,
                 overwrite: Annotated[bool, "If true, overwrite existing table"] = False,
                 fail_on_error: Annotated[bool, "If true, fail on error instead of logging"] = True,
                 batch_size: Annotated[int, "Batch size for committing in the vector database"] = 100,
                 optimize_on_batch: Annotated[bool, "If true, optimize the table after each batch.  Otherwise optimize after last batch."]=False,
                 ):
        super().__init__()
        self.embedding_model = embedding_model
        self.embedding_source = embedding_source
        self.embedding_field = embedding_field
        self.path = path
        self.table_name = table_name
        self.doc_id_field = doc_id_field
        self.overwrite = overwrite
        self.fail_on_error = fail_on_error

        self.pipeline = LLMEmbed(model=self.embedding_model,
                                source=self.embedding_source,
                                field=self.embedding_field,
                                set_as="vector",
                                fail_on_error=self.fail_on_error) | \
                        add_to_lancedb(path=self.path,
                                       table_name=self.table_name,
                                       doc_id_field=self.doc_id_field,
                                       overwrite=self.overwrite,
                                       batch_size=batch_size,
                                       optimize_on_batch=optimize_on_batch,
                                       )

    def transform(self, input_iter):
        yield from self.pipeline.transform(input_iter)


@register_segment("searchVectorDatabase")
class SearchVectorDatabaseSegment(AbstractSegment):
    """Segment to search a vector database in LanceDB.

    This segment can accept either strings or dictionaries as input.
    - If query_field is None: Expects string inputs, which are embedded directly and
      search results are yielded (set_as must be None).
    - If query_field is specified: Expects dictionary inputs, embeds the specified field,
      and search results can be yielded directly (set_as=None) or attached to the input item.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(self,
                 embedding_model: Annotated[str, "Embedding model to use"]=None,
                 embedding_source: Annotated[str, "Source of text to embed"]=None,
                 path: Annotated[str, "Path to LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)"]=None,
                 table_name: Annotated[str, "Name of the table in the database"] = "docs",
                 query_field: Annotated[Optional[str], "Field containing the query text to embed. If None, expects string inputs."] = None,
                 limit: Annotated[int, "Number of search results to return"] = 10,
                 set_as: Annotated[Optional[str], "Field name to store search results. If None, yields results directly. Must be None if query_field is None."] = None,
                 read_consistency_interval: Annotated[int, "Read consistency interval in seconds"] = 10,
                 ):
        super().__init__()
        self.query_field = query_field
        self.embedding_model = embedding_model
        self.embedding_source = embedding_source
        self.path = path
        self.table_name = table_name
        self.limit = limit
        self.set_as = set_as
        self.read_consistency_interval = read_consistency_interval

        # Validate: if query_field is None (string inputs), set_as must also be None
        if self.query_field is None and self.set_as is not None:
            raise ValueError("set_as must be None when query_field is None (string inputs cannot have fields attached)")

        # Build pipeline based on input type
        if self.query_field is None:
            # String inputs: embed directly, yield search results
            self.pipeline = LLMEmbed(model=self.embedding_model,
                                    source=self.embedding_source,
                                    field=None) | \
                            search_lancedb(path=self.path,
                                          table_name=self.table_name,
                                          field=None,
                                          all_results_at_once=True,
                                          limit=self.limit,
                                          read_consistency_interval=self.read_consistency_interval)
        else:
            # Dictionary inputs: embed field
            if self.set_as is not None:
                # Attach search results to input item
                self.pipeline = LLMEmbed(model=self.embedding_model,
                                        source=self.embedding_source,
                                        field=self.query_field,
                                        set_as="vector") | \
                                search_lancedb(path=self.path,
                                              table_name=self.table_name,
                                              field="vector",
                                              all_results_at_once=True,
                                              set_as=self.set_as,
                                              limit=self.limit,
                                              read_consistency_interval=self.read_consistency_interval)
            else:
                # Yield search results directly
                self.pipeline = LLMEmbed(model=self.embedding_model,
                                        source=self.embedding_source,
                                        field=self.query_field) | \
                                search_lancedb(path=self.path,
                                              table_name=self.table_name,
                                              field=None,
                                              all_results_at_once=True,
                                              limit=self.limit,
                                              read_consistency_interval=self.read_consistency_interval)

    def transform(self, input_iter):
        yield from self.pipeline.transform(input_iter)