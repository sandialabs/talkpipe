import logging
from dataclasses import dataclass, field
from typing import Optional, Annotated, Callable
from talkpipe import AbstractSegment, register_segment, segment
from talkpipe.search.lancedb import add_to_lancedb, search_lancedb
from talkpipe.llm.embedding import LLMEmbed
from talkpipe.data.extraction import listFiles, ReadFile
from talkpipe.pipe.io import Print
from talkpipe.pipe.basic import progressTicks, setAs, ToDict
from talkpipe.data.text.chunking_units import ShingleText, splitText
from talkpipe.data.text.cleaning import stripBase64
from talkpipe.util.config import get_config
from talkpipe.util.constants import TALKPIPE_EMBEDDING_MODEL_NAME, TALKPIPE_EMBEDDING_MODEL_SOURCE

logger = logging.getLogger(__name__)


@register_segment("processDocuments")
class ProcessDocumentsSegment(AbstractSegment):
    """Segment to read files, split, shingle, and prepare documents for vector DB ingestion."""

    def __init__(self,
                 chunk_size: Annotated[int, "Size threshold for text chunking"] = 300,
                 shingle_size: Annotated[int, "Size threshold for text chunking shingles"] = 3,
                 overlap: Annotated[int, "Overlap threshold for text chunking shingles"] = 1,
                 strip_base64: Annotated[bool, "If true, strip base64 payloads (e.g. embedded images) from content before chunking"] = True,
                 ):
        super().__init__()
        self.chunk_size = chunk_size
        self.shingle_size = shingle_size
        self.overlap = overlap
        self.strip_base64 = strip_base64

        # listFiles is a segment expecting an iterable of patterns or values, so its input must be the patterns.
        # Store the shingled text as content so retrieved documents contain the same
        # text that was embedded, not just the final split chunk in the shingle.
        # Base64 payloads are stripped before chunking: they embed to degenerate
        # vectors that outrank real content for every query.
        source = (
            listFiles(full_path=True, files_only=True)
            | Print()
            | ReadFile()
        )
        if self.strip_base64:
            source = source | stripBase64(field='content', set_as='content')
        self.pipeline = (
            source
            | splitText(field='content', set_as='content', criteria=self.chunk_size)
            | ShingleText(field='content', set_as='shingle_text', key='source', shingle_size=self.shingle_size, overlap=self.overlap, size_mode='count', delimiter=' ')
            | ToDict(field_list="content,source,id,title,shingle_text")
            | setAs(field_list="shingle_text:content")
            | progressTicks(tick=".", tick_count=1, eol_count=50)
        )

    def transform(self, input_iter):
        yield from self.pipeline.transform(input_iter)


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
                 optimize_every: Annotated[int, "Optimize the table after at least this many rows have been added since the last optimization. 0 disables periodic optimization."]=5000,
                 on_token_overflow: Annotated[str, "When embedding fails as too long: error, truncate (shrink and retry), or chunk_pool"]="error",
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
                                fail_on_error=self.fail_on_error,
                                on_token_overflow=on_token_overflow) | \
                        add_to_lancedb(path=self.path,
                                       table_name=self.table_name,
                                       doc_id_field=self.doc_id_field,
                                       overwrite=self.overwrite,
                                       batch_size=batch_size,
                                       optimize_on_batch=optimize_on_batch,
                                       optimize_every=optimize_every,
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

class RagIngestError(RuntimeError):
    """A RAG database build failed for a reason the caller should surface."""


class EmbedderPreflightError(RagIngestError):
    """The embedder failed a test embedding before any documents were read."""


class EmbeddingDimensionMismatchError(RagIngestError):
    """The embedder's vector dimension does not match the existing database.

    Carries the expected (existing database) and actual (current embedder)
    dimensions so callers can build their own guidance messages.
    """

    def __init__(self, message: str, *, expected: int, actual: int):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


@dataclass
class RagIngestResult:
    """Outcome of one build_rag_database run.

    chunks_skipped counts chunks that were extracted from documents but
    dropped because their embedding failed; dimension is the embedding
    vector length observed during preflight (None when preflight is off).
    """

    chunks_indexed: int
    chunks_skipped: int
    files_indexed: int
    embedding_source: str
    embedding_model: str
    dimension: Optional[int]


@dataclass
class _IngestTally:
    """Counters shared by the tally segments across one build_rag_database run.

    chunks_extracted counts chunks entering the embedder. LLMEmbed with
    fail_on_error false silently drops chunks whose embedding fails, so each
    stored chunk infers the drops since the previous one by comparing
    chunks_extracted against extracted_at_last_store.
    """

    chunks_extracted: int = 0
    chunks_indexed: int = 0
    chunks_skipped: int = 0
    extracted_at_last_store: int = 0
    seen_sources: set = field(default_factory=set)


@segment()
def _tally_extracted_chunks(items, tally: _IngestTally):
    """Pass chunks through unchanged, counting them as they enter the embedder."""
    for item in items:
        tally.chunks_extracted += 1
        yield item


@segment()
def _tally_stored_chunks(items, tally: _IngestTally, progress=None):
    """Pass stored chunks through, tracking skips, files, and progress.

    Expects the dict items produced by ProcessDocumentsSegment (a "source"
    field identifies the originating file) after they have been stored.
    The optional progress callback receives (chunks_done, files_done,
    current_source_path) per stored chunk.
    """
    for item in items:
        tally.chunks_indexed += 1
        # Chunks consumed since the last stored one, minus this one, failed
        # to embed and were dropped by LLMEmbed when fail_on_error is false.
        tally.chunks_skipped += tally.chunks_extracted - tally.extracted_at_last_store - 1
        tally.extracted_at_last_store = tally.chunks_extracted
        source = str(item.get("source") or "") if isinstance(item, dict) else ""
        if source:
            tally.seen_sources.add(source)
        if progress is not None:
            progress(tally.chunks_indexed, len(tally.seen_sources), source)
        yield item


def build_rag_database(
    source_pattern,
    path: str,
    embedding_model: Optional[str] = None,
    embedding_source: Optional[str] = None,
    *,
    table_name: str = "docs",
    embedding_field: str = "shingle_text",
    chunk_size: int = 300,
    shingle_size: int = 3,
    overlap: int = 1,
    doc_id_field: Optional[str] = None,
    overwrite: bool = False,
    batch_size: int = 100,
    fail_on_error: bool = False,
    on_token_overflow: str = "truncate",
    expected_dimension: Optional[int] = None,
    preflight: bool = True,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> RagIngestResult:
    """Build a RAG vector database from documents matching a glob pattern.

    The single shared ingestion driver behind the makevectordatabase CLI and
    downstream applications (e.g. talkpipe-vault): documents are read,
    chunked, and shingled by ProcessDocumentsSegment, embedded by LLMEmbed,
    and stored in LanceDB by add_to_lancedb.

    Robustness contract, in contrast to composing the segments by hand:

    - Preflight: a test string is embedded before any documents are read, so
      an unreachable or misconfigured embedder fails immediately
      (EmbedderPreflightError) instead of paying a provider timeout per chunk
      and finishing with an empty database. When expected_dimension is given
      (e.g. read from metadata recorded at first build), a differing probe
      vector length raises EmbeddingDimensionMismatchError up front instead
      of failing on the first LanceDB write.
    - Over-long chunks are truncated and indexed by default rather than
      aborting the run (LLMEmbed's on_token_overflow="error" default raises
      even when fail_on_error is false).
    - Chunks whose embedding fails are counted and reported via
      RagIngestResult.chunks_skipped rather than dropped silently; if chunks
      were extracted but none embedded, RagIngestError is raised so callers
      cannot mistake a dead embedder for empty documents.

    The optional progress callback receives (chunks_done, files_done,
    current_source_path) as chunks are stored.
    """
    config = get_config()
    embedding_model = embedding_model or config.get(TALKPIPE_EMBEDDING_MODEL_NAME)
    embedding_source = embedding_source or config.get(TALKPIPE_EMBEDDING_MODEL_SOURCE)

    embed_segment = LLMEmbed(
        model=embedding_model,
        source=embedding_source,
        field=embedding_field,
        set_as="vector",
        fail_on_error=fail_on_error,
        on_token_overflow=on_token_overflow,
    )

    dimension: Optional[int] = None
    if preflight:
        try:
            vector = embed_segment.embedder.execute_one("talkpipe embedder preflight")
        except Exception as exc:
            raise EmbedderPreflightError(
                f"a test embedding with {embedding_source}/{embedding_model} "
                f"failed before any documents were read; check that the "
                f"embedding model is configured correctly and that the "
                f"provider is reachable. Provider error: {exc}"
            ) from exc
        dimension = len(vector) if vector is not None else None
        if expected_dimension and dimension and dimension != expected_dimension:
            raise EmbeddingDimensionMismatchError(
                f"the existing database at '{path}' holds "
                f"{expected_dimension}-dimensional vectors, but "
                f"{embedding_source}/{embedding_model} produces "
                f"{dimension}-dimensional vectors; adding to it would fail. "
                f"Rebuild with overwrite, or restore the original embedder.",
                expected=expected_dimension,
                actual=dimension,
            )

    tally = _IngestTally()
    pipeline = (
        ProcessDocumentsSegment(
            chunk_size=chunk_size,
            shingle_size=shingle_size,
            overlap=overlap,
        )
        | _tally_extracted_chunks(tally=tally)
        | embed_segment
        | add_to_lancedb(
            path=path,
            table_name=table_name,
            doc_id_field=doc_id_field,
            overwrite=overwrite,
            batch_size=batch_size,
        )
        | _tally_stored_chunks(tally=tally, progress=progress)
    )

    patterns = [source_pattern] if isinstance(source_pattern, str) else list(source_pattern)
    for _ in pipeline.transform(patterns):
        pass
    # Chunks consumed after the last stored one also failed to embed.
    tally.chunks_skipped += tally.chunks_extracted - tally.extracted_at_last_store

    if tally.chunks_indexed == 0 and tally.chunks_extracted > 0:
        raise RagIngestError(
            f"{tally.chunks_extracted} chunk(s) were extracted from the matched "
            f"documents, but none could be embedded with "
            f"{embedding_source}/{embedding_model}; check the log for the "
            f"embedding errors."
        )
    return RagIngestResult(
        chunks_indexed=tally.chunks_indexed,
        chunks_skipped=tally.chunks_skipped,
        files_indexed=len(tally.seen_sources),
        embedding_source=embedding_source,
        embedding_model=embedding_model,
        dimension=dimension,
    )
