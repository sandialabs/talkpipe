"""Basic RAG pipeline implementation"""

import logging
from abc import abstractmethod
from collections.abc import Iterable, Iterator
from typing import Annotated, Any

from talkpipe import AbstractSegment, register_segment
from talkpipe.llm.chat import LlmBinaryAnswer, LLMPrompt, LlmScore
from talkpipe.pipe.basic import DiagPrint
from talkpipe.pipelines.vector_databases import SearchVectorDatabaseSegment
from talkpipe.search.abstract import SearchResult
from talkpipe.util.data_manipulation import assign_property, extract_property

logger = logging.getLogger(__name__)


def _extract_source_paths(background: list[Any]) -> list[str]:
    """Extract unique source paths (or titles) from search results for citation."""
    seen = set()
    paths = []
    for result in background:
        if not isinstance(result, SearchResult) or not result.document:
            continue
        doc = result.document
        # Prefer source (full path), fallback to title (filename)
        p = doc.get("source") or doc.get("title")
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


# Default system prompts for RAG pipelines
DEFAULT_RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on provided background information.
Ground your responses in the background context given. When citing information, include the source using the title or path (source) from the background when available.
If the background does not contain sufficient information to answer the question, acknowledge this limitation rather than speculating or making up information.
Be concise and accurate in your responses."""

DEFAULT_BINARY_ANSWER_SYSTEM_PROMPT = "Answer the question with YES (true) or NO (false) based on the provided information. Provide a brief explanation for your answer."

DEFAULT_SCORE_SYSTEM_PROMPT = "Evaluate the provided content and assign an integer score with a brief explanation. The score should reflect the evaluation criteria specified in the user prompt."


def construct_background(
    background: Annotated[
        str | list[str | SearchResult],
        "Background items against which relevance is evaluated",
    ],
) -> str:
    """Construct background from input

    Args:
        background: Background input

    Returns:
        The background text block
    """
    ans: list[str] = []
    if isinstance(background, str):
        ans.append(background)
    else:
        for item in background:
            if isinstance(item, str):
                ans.append(item)
            elif isinstance(item, SearchResult):
                ans.append(
                    item.prompt_worthy_string(priority_fields=["title", "source"])
                )
            else:
                raise ValueError(f"Unsupported background item type: {type(item)}")
    return "Background:\n" + "\n\n".join(ans)


@register_segment("constructRagPrompt")
class ConstructRAGPrompt(AbstractSegment[Any, Any]):
    def __init__(
        self,
        content_field: Annotated[Any, "Field to evaluate relevance on"],
        prompt_directive: Annotated[str, "Directive to guide the evaluation"],
        background_field: Annotated[str, "Field containing background items"],
        set_as: Annotated[str | None, "The field to set/append the result as."] = None,
    ):
        super().__init__()
        self.background_field = background_field
        self.content_field = content_field
        self.set_as = set_as
        self.prompt_directive = prompt_directive

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        for item in input_iter:
            background = construct_background(
                extract_property(item, self.background_field)
            )
            content = extract_property(item, self.content_field)

            prompt = f"{background}\n\n{self.prompt_directive}\n\nContent:\n{content}"
            if self.set_as:
                assign_property(item, self.set_as, prompt)
                yield item
            else:
                yield prompt


@register_segment("appendRagSources")
class AppendRAGSources(AbstractSegment[Any, Any]):
    """Appends source file paths from _background to the RAG response in _rag_response, storing the result in set_as while preserving the item structure."""

    def __init__(
        self,
        partial_answer_field: Annotated[str, "Field with the llm response"],
        set_as: Annotated[
            str | None, "Field to store the answer (with sources appended)"
        ] = None,
    ):
        super().__init__()
        self.set_as = set_as
        self.partial_answer_field = partial_answer_field

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        for item in input_iter:
            response = extract_property(
                item, self.partial_answer_field, fail_on_missing=False
            )
            background = extract_property(item, "_background", fail_on_missing=False)
            if response is None:
                yield item
                continue
            text = str(response)
            if background and isinstance(background, list):
                paths = _extract_source_paths(background)
                if paths:
                    text += "\n\nSources:\n" + "\n".join(f"- {p}" for p in paths)
            if self.set_as is None:
                yield text
            else:
                assign_property(item, self.set_as, text)
                yield item


class AbstractRAGPipeline(AbstractSegment[Any, Any]):
    """Convenience segment that runs a RAG pipeline from search to prompt creation to LLM completion.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(
        self,
        path: Annotated[
            str,
            "Path to LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)",
        ],
        content_field: Annotated[Any, "Field to evaluate relevance on"],
        embedding_prompt: Annotated[
            str | None,
            "Prompt to use for embedding.  If None (default), use the content_field.",
        ] = None,
        embedding_model: Annotated[str | None, "Embedding model to use"] = None,
        embedding_source: Annotated[str | None, "Source of text to embed"] = None,
        completion_model: Annotated[
            str | None, "LLM model to use for completion"
        ] = None,
        completion_source: Annotated[
            str | None, "Source of prompt for completion"
        ] = None,
        prompt_directive: Annotated[
            str, "Directive to guide the evaluation"
        ] = "Respond to the provided content based on the background information. If the background does not contain relevant information, respond with 'No relevant information found.'",
        system_prompt: Annotated[
            str | None, "System prompt for the completion LLM"
        ] = None,
        set_as: Annotated[str | None, "The field to set/append the result as."] = None,
        limit: Annotated[int, "Number of search results to retrieve"] = 5,
        table_name: Annotated[
            str, "Name of the table in the LanceDB database"
        ] = "docs",
        read_consistency_interval: Annotated[
            int, "Read consistency interval in seconds"
        ] = 10,
        diagPrintOutput: Annotated[
            str | None, "DiagPrint output target (stdout, stderr, or a logger name)"
        ] = None,
        logging_level: Annotated[int, "Logging level for the pipeline"] = logging.DEBUG,
        role_map: Annotated[
            str | None, "Initial conversation context as 'role:message,role:message'"
        ] = None,
        memory_mode: Annotated[
            str,
            "Memory behavior: full, recent_only, summary_llm, summary_deterministic, or summary_truncate",
        ] = "full",
        unsummarized_message_count: Annotated[
            int, "Recent message count kept out of summary compaction"
        ] = 6,
        context_token_trigger: Annotated[
            float | None,
            "Approximate context-token trigger for rolling memory compaction (values < 1 are ignored)",
        ] = None,
        memory_size: Annotated[
            int, "Target max tokens for generated summary memory"
        ] = 512,
        debug_messages: Annotated[
            bool, "Whether to log outbound LLM request messages"
        ] = False,
    ):

        super().__init__()
        self.embedding_model = embedding_model
        self.embedding_source = embedding_source
        self.path = path
        self.completion_model = completion_model
        self.completion_source = completion_source
        self.prompt_directive = prompt_directive
        self.system_prompt = system_prompt
        self.content_field = content_field
        self.embedding_prompt = embedding_prompt or content_field
        self.set_as = set_as
        self.limit = limit
        self.table_name = table_name
        self.read_consistency_interval = read_consistency_interval
        self.diagPrintOutput = diagPrintOutput
        self.logging_level = logging_level
        self.role_map = role_map
        self.memory_mode = memory_mode
        self.unsummarized_message_count = unsummarized_message_count
        self.context_token_trigger = context_token_trigger
        self.memory_size = memory_size
        self.debug_messages = debug_messages
        self._pipeline: AbstractSegment[Any, Any] | None = None

    @abstractmethod
    def make_completion_segment(self) -> AbstractSegment[Any, Any]:
        """Create the segment that performs the completion over the RAG prompt."""

    def make_pipeline(self) -> AbstractSegment[Any, Any]:
        """Build a fresh search -> prompt -> completion pipeline.

        Each call returns independent segments (its own database connection
        and its own LLM adapter, hence its own conversation memory). ``transform``
        builds one lazily and keeps it; callers that need isolated state per
        user, such as ``serverag``, call this once per session instead.
        """
        pipeline: AbstractSegment[Any, Any] = (
            SearchVectorDatabaseSegment(
                embedding_model=self.embedding_model,
                embedding_source=self.embedding_source,
                path=self.path,
                table_name=self.table_name,
                set_as="_background",
                limit=self.limit,
                query_field=self.embedding_prompt,
                read_consistency_interval=self.read_consistency_interval,
            )
            | DiagPrint(output=self.diagPrintOutput, level=self.logging_level)
            | ConstructRAGPrompt(
                prompt_directive=self.prompt_directive,
                background_field="_background",
                content_field=self.content_field,
                set_as="_ragprompt",
            )
            | DiagPrint(output=self.diagPrintOutput, level=self.logging_level)
            | self.make_completion_segment()
        )
        return pipeline

    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        # Built once and reused, like every other stateful segment: rebuilding
        # per call reconnected to the database and replaced the LLM adapter,
        # which silently reset multi-turn conversation memory between calls.
        if self._pipeline is None:
            self._pipeline = self.make_pipeline()
        yield from self._pipeline(input_iter)


@register_segment("ragToText")
class RAGToText(AbstractRAGPipeline):
    """RAG pipeline that outputs text completions from LLM.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(
        self,
        path: Annotated[
            str,
            "Path to LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)",
        ],
        content_field: Annotated[Any, "Field to evaluate relevance on"],
        embedding_prompt: Annotated[
            str | None,
            "Prompt to use for embedding.  If None (default), use the content_field.",
        ] = None,
        embedding_model: Annotated[str | None, "Embedding model to use"] = None,
        embedding_source: Annotated[str | None, "Source of text to embed"] = None,
        completion_model: Annotated[
            str | None, "LLM model to use for completion"
        ] = None,
        completion_source: Annotated[
            str | None, "Source of prompt for completion"
        ] = None,
        prompt_directive: Annotated[
            str, "Directive to guide the evaluation"
        ] = "Respond to the provided content based on the background information. If the background does not contain relevant information, respond with 'No relevant information found.'",
        system_prompt: Annotated[
            str, "System prompt for the completion LLM"
        ] = DEFAULT_RAG_SYSTEM_PROMPT,
        set_as: Annotated[str | None, "The field to set/append the result as."] = None,
        limit: Annotated[int, "Number of search results to retrieve"] = 10,
        table_name: Annotated[
            str, "Name of the table in the LanceDB database"
        ] = "docs",
        read_consistency_interval: Annotated[
            int, "Read consistency interval in seconds"
        ] = 10,
        diagPrintOutput: Annotated[
            str | None, "DiagPrint output target (stdout, stderr, or a logger name)"
        ] = None,
        logging_level: Annotated[int, "Logging level for the pipeline"] = logging.DEBUG,
        role_map: Annotated[
            str | None, "Initial conversation context as 'role:message,role:message'"
        ] = None,
        memory_mode: Annotated[
            str,
            "Memory behavior: full, recent_only, summary_llm, summary_deterministic, or summary_truncate",
        ] = "full",
        unsummarized_message_count: Annotated[
            int, "Recent message count kept out of summary compaction"
        ] = 6,
        context_token_trigger: Annotated[
            float | None,
            "Approximate context-token trigger for rolling memory compaction (values < 1 are ignored)",
        ] = None,
        memory_size: Annotated[
            int, "Target max tokens for generated summary memory"
        ] = 512,
        debug_messages: Annotated[
            bool, "Whether to log outbound LLM request messages"
        ] = False,
        append_sources_to_output: Annotated[
            bool, "If True, append source file paths to the answer"
        ] = True,
    ):
        super().__init__(
            embedding_model=embedding_model,
            embedding_source=embedding_source,
            completion_model=completion_model,
            completion_source=completion_source,
            path=path,
            content_field=content_field,
            embedding_prompt=embedding_prompt,
            prompt_directive=prompt_directive,
            system_prompt=system_prompt,
            set_as=set_as,
            limit=limit,
            table_name=table_name,
            read_consistency_interval=read_consistency_interval,
            diagPrintOutput=diagPrintOutput,
            logging_level=logging_level,
            role_map=role_map,
            memory_mode=memory_mode,
            unsummarized_message_count=unsummarized_message_count,
            context_token_trigger=context_token_trigger,
            memory_size=memory_size,
            debug_messages=debug_messages,
        )
        self.append_sources_to_output = append_sources_to_output

    def make_completion_segment(self) -> AbstractSegment[Any, Any]:
        if not self.append_sources_to_output:
            return self._make_llm_prompt(set_as=self.set_as)
        partial_answer_field = "_partial_rag_response"
        return self._make_llm_prompt(set_as=partial_answer_field) | AppendRAGSources(
            partial_answer_field=partial_answer_field,
            set_as=self.set_as,
        )

    def _make_llm_prompt(self, set_as: str | None) -> LLMPrompt:
        return LLMPrompt(
            model=self.completion_model,
            source=self.completion_source,
            system_prompt=self.system_prompt,
            field="_ragprompt",
            set_as=set_as,
            role_map=self.role_map,
            memory_mode=self.memory_mode,
            unsummarized_message_count=self.unsummarized_message_count,
            context_token_trigger=self.context_token_trigger,
            memory_size=self.memory_size,
            debug_messages=self.debug_messages,
        )


@register_segment("ragToBinaryAnswer")
class RAGToBinaryAnswer(AbstractRAGPipeline):
    """RAG pipeline that outputs binary answers from LLM.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    # This pipeline always has a system prompt (defaulted), unlike the base class.
    system_prompt: str

    def __init__(
        self,
        embedding_model: Annotated[str, "Embedding model to use"],
        embedding_source: Annotated[str, "Source of text to embed"],
        completion_model: Annotated[str, "LLM model to use for completion"],
        completion_source: Annotated[str, "Source of prompt for completion"],
        path: Annotated[
            str,
            "Path to LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)",
        ],
        content_field: Annotated[Any, "Field to evaluate relevance on"],
        embedding_prompt: Annotated[
            str | None,
            "Prompt to use for embedding.  If None (default), use the content_field.",
        ] = None,
        prompt_directive: Annotated[
            str, "Directive to guide the evaluation"
        ] = "Answer the provided question as YES or NO. If the background does not contain relevant information, respond with 'NO'.",
        system_prompt: Annotated[
            str, "System prompt for the completion LLM"
        ] = DEFAULT_BINARY_ANSWER_SYSTEM_PROMPT,
        set_as: Annotated[str | None, "The field to set/append the result as."] = None,
        limit: Annotated[int, "Number of search results to retrieve"] = 10,
        table_name: Annotated[
            str, "Name of the table in the LanceDB database"
        ] = "docs",
        read_consistency_interval: Annotated[
            int, "Read consistency interval in seconds"
        ] = 10,
        diagPrintOutput: Annotated[
            str | None, "DiagPrint output target (stdout, stderr, or a logger name)"
        ] = None,
        logging_level: Annotated[int, "Logging level for the pipeline"] = logging.DEBUG,
        role_map: Annotated[
            str | None, "Initial conversation context as 'role:message,role:message'"
        ] = None,
        memory_mode: Annotated[
            str,
            "Memory behavior: full, recent_only, summary_llm, summary_deterministic, or summary_truncate",
        ] = "full",
        unsummarized_message_count: Annotated[
            int, "Recent message count kept out of summary compaction"
        ] = 6,
        context_token_trigger: Annotated[
            float | None,
            "Approximate context-token trigger for rolling memory compaction (values < 1 are ignored)",
        ] = None,
        memory_size: Annotated[
            int, "Target max tokens for generated summary memory"
        ] = 512,
        debug_messages: Annotated[
            bool, "Whether to log outbound LLM request messages"
        ] = False,
    ):
        super().__init__(
            embedding_model=embedding_model,
            embedding_source=embedding_source,
            completion_model=completion_model,
            completion_source=completion_source,
            path=path,
            content_field=content_field,
            embedding_prompt=embedding_prompt,
            prompt_directive=prompt_directive,
            system_prompt=system_prompt,
            set_as=set_as,
            limit=limit,
            table_name=table_name,
            read_consistency_interval=read_consistency_interval,
            diagPrintOutput=diagPrintOutput,
            logging_level=logging_level,
            role_map=role_map,
            memory_mode=memory_mode,
            unsummarized_message_count=unsummarized_message_count,
            context_token_trigger=context_token_trigger,
            memory_size=memory_size,
            debug_messages=debug_messages,
        )

    def make_completion_segment(self) -> AbstractSegment[Any, Any]:
        return LlmBinaryAnswer(
            system_prompt=self.system_prompt,
            model=self.completion_model,
            source=self.completion_source,
            field="_ragprompt",
            set_as=self.set_as,
            role_map=self.role_map,
            memory_mode=self.memory_mode,
            unsummarized_message_count=self.unsummarized_message_count,
            context_token_trigger=self.context_token_trigger,
            memory_size=self.memory_size,
            debug_messages=self.debug_messages,
        )


@register_segment("ragToScore")
class RAGToScore(AbstractRAGPipeline):
    """RAG pipeline that outputs scores from LLM.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    # This pipeline always has a system prompt (defaulted), unlike the base class.
    system_prompt: str

    def __init__(
        self,
        embedding_model: Annotated[str, "Embedding model to use"],
        embedding_source: Annotated[str, "Source of text to embed"],
        completion_model: Annotated[str, "LLM model to use for completion"],
        completion_source: Annotated[str, "Source of prompt for completion"],
        path: Annotated[
            str,
            "Path to LanceDB database. Supports file paths or 'tmp://name' for process-scoped temp (auto-cleanup)",
        ],
        content_field: Annotated[Any, "Field to evaluate relevance on"],
        embedding_prompt: Annotated[
            str | None,
            "Prompt to use for embedding.  If None (default), use the content_field.",
        ] = None,
        prompt_directive: Annotated[
            str, "Directive to guide the evaluation"
        ] = "Answer the provided question on a scale of 1 to 10. If the background does not contain relevant information, respond with a score of 1.",
        system_prompt: Annotated[
            str, "System prompt for the completion LLM"
        ] = DEFAULT_SCORE_SYSTEM_PROMPT,
        set_as: Annotated[str | None, "The field to set/append the result as."] = None,
        limit: Annotated[int, "Number of search results to retrieve"] = 10,
        table_name: Annotated[
            str, "Name of the table in the LanceDB database"
        ] = "docs",
        read_consistency_interval: Annotated[
            int, "Read consistency interval in seconds"
        ] = 10,
        diagPrintOutput: Annotated[
            str | None, "DiagPrint output target (stdout, stderr, or a logger name)"
        ] = None,
        logging_level: Annotated[int, "Logging level for the pipeline"] = logging.DEBUG,
        role_map: Annotated[
            str | None, "Initial conversation context as 'role:message,role:message'"
        ] = None,
        memory_mode: Annotated[
            str,
            "Memory behavior: full, recent_only, summary_llm, summary_deterministic, or summary_truncate",
        ] = "full",
        unsummarized_message_count: Annotated[
            int, "Recent message count kept out of summary compaction"
        ] = 6,
        context_token_trigger: Annotated[
            float | None,
            "Approximate context-token trigger for rolling memory compaction (values < 1 are ignored)",
        ] = None,
        memory_size: Annotated[
            int, "Target max tokens for generated summary memory"
        ] = 512,
        debug_messages: Annotated[
            bool, "Whether to log outbound LLM request messages"
        ] = False,
    ):
        super().__init__(
            embedding_model=embedding_model,
            embedding_source=embedding_source,
            completion_model=completion_model,
            completion_source=completion_source,
            path=path,
            content_field=content_field,
            embedding_prompt=embedding_prompt,
            prompt_directive=prompt_directive,
            system_prompt=system_prompt,
            set_as=set_as,
            limit=limit,
            table_name=table_name,
            read_consistency_interval=read_consistency_interval,
            diagPrintOutput=diagPrintOutput,
            logging_level=logging_level,
            role_map=role_map,
            memory_mode=memory_mode,
            unsummarized_message_count=unsummarized_message_count,
            context_token_trigger=context_token_trigger,
            memory_size=memory_size,
            debug_messages=debug_messages,
        )

    def make_completion_segment(self) -> AbstractSegment[Any, Any]:
        return LlmScore(
            system_prompt=self.system_prompt,
            model=self.completion_model,
            source=self.completion_source,
            field="_ragprompt",
            set_as=self.set_as,
            role_map=self.role_map,
            memory_mode=self.memory_mode,
            unsummarized_message_count=self.unsummarized_message_count,
            context_token_trigger=self.context_token_trigger,
            memory_size=self.memory_size,
            debug_messages=self.debug_messages,
        )
