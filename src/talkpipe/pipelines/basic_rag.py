""" Basic RAG pipeline implementation """
from typing import Annotated, List, Union, Any
import logging
from abc import ABC, abstractmethod
from talkpipe import AbstractSegment, AbstractFieldSegment, register_segment
from talkpipe.search.abstract import SearchResult
from talkpipe.llm.chat import LlmScore, LLMPrompt, LlmBinaryAnswer
from talkpipe.util.data_manipulation import extract_property, assign_property
from talkpipe.pipelines.vector_databases import SearchVectorDatabaseSegment

logger = logging.getLogger(__name__)

def construct_background(background: Annotated[Union[str, List[Union[str, SearchResult]]], "Background items against which relevance is evaluated"]) -> List[Union[str, SearchResult]]:
    """ Construct background from input

    Args:
        background: Background input

    Returns:
        List of background items
    """
    ans = []
    if isinstance(background, str):
        ans.append(background)
    else:
        for item in background:
            if isinstance(item, str):
                ans.append(item)
            elif isinstance(item, SearchResult):
                ans.append(item.prompt_worthy_string(priority_fields=["title"]))
            else:
                raise ValueError(f"Unsupported background item type: {type(item)}")
    return "Background:\n" + "\n\n".join(ans)

@register_segment("constructRagPrompt")
class ConstructRAGPrompt(AbstractSegment):
    def __init__(self, 
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"],
                 background_field: Annotated[str, "Field containing background items"],
                 set_as: Annotated[str, "The field to set/append the result as."] = None):
        super().__init__()
        self.background_field = background_field
        self.content_field = content_field
        self.set_as = set_as
        self.prompt_directive = prompt_directive


    def transform(self, input_iter):
        for item in input_iter:
            background = construct_background(extract_property(item, self.background_field))
            content = extract_property(item, self.content_field)

            prompt = f"{self.prompt_directive}\n\n{background}\n\nContent:\n{content}"
            if self.set_as:
                assign_property(item, self.set_as, prompt)
                yield item
            else:
                yield prompt


class AbstractRAGPipeline(AbstractSegment):
    """ Convenience segment that runs a RAG pipeline from search to prompt creation to LLM completion.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Memory: "memory://" - Ephemeral in-memory database (faster, no disk I/O)
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(self,
                 path: Annotated[str, "Path to LanceDB database. Supports file paths, 'memory://' for in-memory, or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
                 embedding_prompt: Annotated[str, "Prompt to use for embedding.  If None (default), use the content_field."] = None,
                 embedding_model: Annotated[str, "Embedding model to use"] = None,
                 embedding_source: Annotated[str, "Source of text to embed"] = None,
                 completion_model: Annotated[str, "LLM model to use for completion"] = None,
                 completion_source: Annotated[str, "Source of prompt for completion"] = None,
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"] = "Respond to the provided content based on the background information. If the background does not contain relevant information, respond with 'No relevant information found.'",
                 set_as: Annotated[str, "The field to set/append the result as."] = None,
                 limit: Annotated[int, "Number of search results to retrieve"] = 10,
                 table_name: Annotated[str, "Name of the table in the LanceDB database"] = "docs",
                 read_consistency_interval: Annotated[int, "Read consistency interval in seconds"] = 10):

        super().__init__()
        self.embedding_model = embedding_model
        self.embedding_source = embedding_source
        self.path = path
        self.completion_model = completion_model
        self.completion_source = completion_source
        self.prompt_directive = prompt_directive
        self.content_field = content_field
        self.embedding_prompt = embedding_prompt or content_field
        self.set_as = set_as
        self.limit = limit
        self.table_name = table_name
        self.read_consistency_interval = read_consistency_interval

    @abstractmethod
    def make_completion_segment(self) -> AbstractSegment:
        """ Create the segment that performs the completion over the RAG prompt.
        """

    def make_pipeline(self):
        return SearchVectorDatabaseSegment(embedding_model=self.embedding_model,
                                                    embedding_source=self.embedding_source,
                                                    path=self.path,
                                                    table_name=self.table_name,
                                                    set_as="_background",
                                                    limit=self.limit,
                                                    query_field=self.embedding_prompt,
                                                    read_consistency_interval=self.read_consistency_interval) | \
                        ConstructRAGPrompt(prompt_directive=self.prompt_directive,
                                            background_field="_background",
                                            content_field=self.content_field,
                                            set_as="_ragprompt") | \
                        self.make_completion_segment()

    def transform(self, input_iter):
        pipeline = self.make_pipeline()
        yield from pipeline(input_iter)

@register_segment("ragToText")
class RAGToText(AbstractRAGPipeline):
    """ RAG pipeline that outputs text completions from LLM.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Memory: "memory://" - Ephemeral in-memory database (faster, no disk I/O)
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(self,
                 path: Annotated[str, "Path to LanceDB database. Supports file paths, 'memory://' for in-memory, or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
                 embedding_prompt: Annotated[str, "Prompt to use for embedding.  If None (default), use the content_field."] = None,
                 embedding_model: Annotated[str, "Embedding model to use"] = None,
                 embedding_source: Annotated[str, "Source of text to embed"] = None,
                 completion_model: Annotated[str, "LLM model to use for completion"] = None,
                 completion_source: Annotated[str, "Source of prompt for completion"] = None,
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"] = "Respond to the provided content based on the background information. If the background does not contain relevant information, respond with 'No relevant information found.'",
                 set_as: Annotated[str, "The field to set/append the result as."] = None,
                 limit: Annotated[int, "Number of search results to retrieve"] = 10,
                 table_name: Annotated[str, "Name of the table in the LanceDB database"] = "docs",
                 read_consistency_interval: Annotated[int, "Read consistency interval in seconds"] = 10):
        super().__init__(embedding_model=embedding_model,
                         embedding_source=embedding_source,
                         completion_model=completion_model,
                         completion_source=completion_source,
                         path=path,
                         content_field=content_field,
                         embedding_prompt=embedding_prompt,
                         prompt_directive=prompt_directive,
                         set_as=set_as,
                         limit=limit,
                         table_name=table_name,
                         read_consistency_interval=read_consistency_interval)
        
    def make_completion_segment(self) -> AbstractSegment:
        return LLMPrompt(model=self.completion_model,
                         source=self.completion_source,
                         field="_ragprompt",
                         set_as=self.set_as)
    
@register_segment("ragToBinaryAnswer")
class RAGToBinaryAnswer(AbstractRAGPipeline):
    """ RAG pipeline that outputs binary answers from LLM.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Memory: "memory://" - Ephemeral in-memory database (faster, no disk I/O)
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(self,
                 embedding_model: Annotated[str, "Embedding model to use"],
                 embedding_source: Annotated[str, "Source of text to embed"],
                 completion_model: Annotated[str, "LLM model to use for completion"],
                 completion_source: Annotated[str, "Source of prompt for completion"],
                 path: Annotated[str, "Path to LanceDB database. Supports file paths, 'memory://' for in-memory, or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
                 embedding_prompt: Annotated[str, "Prompt to use for embedding.  If None (default), use the content_field."] = None,
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"] = "Answer the provided question as YES or NO. If the background does not contain relevant information, respond with 'NO'.",
                 set_as: Annotated[str, "The field to set/append the result as."] = None,
                 limit: Annotated[int, "Number of search results to retrieve"] = 10,
                 table_name: Annotated[str, "Name of the table in the LanceDB database"] = "docs",
                 read_consistency_interval: Annotated[int, "Read consistency interval in seconds"] = 10):
        super().__init__(embedding_model=embedding_model,
                         embedding_source=embedding_source,
                         completion_model=completion_model,
                         completion_source=completion_source,
                         path=path,
                         content_field=content_field,
                         embedding_prompt=embedding_prompt,
                         prompt_directive=prompt_directive,
                         set_as=set_as,
                         limit=limit,
                         table_name=table_name,
                         read_consistency_interval=read_consistency_interval)

    def make_completion_segment(self) -> AbstractSegment:
        return LlmBinaryAnswer(system_prompt="Answer the question with YES (true) or NO (false) based on the provided information. Provide a brief explanation for your answer.",
                               model=self.completion_model,
                               source=self.completion_source,
                               field="_ragprompt",
                               set_as=self.set_as)

@register_segment("ragToScore")
class RAGToScore(AbstractRAGPipeline):
    """ RAG pipeline that outputs scores from LLM.

    Path supports multiple URI schemes:
    - File path: "./my_db" or "/path/to/db" - Persistent storage
    - Memory: "memory://" - Ephemeral in-memory database (faster, no disk I/O)
    - Temp: "tmp://name" - Process-scoped temporary database (shared by name, auto-cleanup on exit)
    """

    def __init__(self,
                 embedding_model: Annotated[str, "Embedding model to use"],
                 embedding_source: Annotated[str, "Source of text to embed"],
                 completion_model: Annotated[str, "LLM model to use for completion"],
                 completion_source: Annotated[str, "Source of prompt for completion"],
                 path: Annotated[str, "Path to LanceDB database. Supports file paths, 'memory://' for in-memory, or 'tmp://name' for process-scoped temp (auto-cleanup)"],
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
                 embedding_prompt: Annotated[str, "Prompt to use for embedding.  If None (default), use the content_field."] = None,
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"] = "Answer the provided question on a scale of 1 to 10. If the background does not contain relevant information, respond with a score of 1.",
                 set_as: Annotated[str, "The field to set/append the result as."] = None,
                 limit: Annotated[int, "Number of search results to retrieve"] = 10,
                 table_name: Annotated[str, "Name of the table in the LanceDB database"] = "docs",
                 read_consistency_interval: Annotated[int, "Read consistency interval in seconds"] = 10):
        super().__init__(embedding_model=embedding_model,
                         embedding_source=embedding_source,
                         completion_model=completion_model,
                         completion_source=completion_source,
                         path=path,
                         content_field=content_field,
                         embedding_prompt=embedding_prompt,
                         prompt_directive=prompt_directive,
                         set_as=set_as,
                         limit=limit,
                         table_name=table_name,
                         read_consistency_interval=read_consistency_interval)

    def make_completion_segment(self) -> AbstractSegment:
        return LlmScore(system_prompt="Evaluate the provided content and assign an integer score with a brief explanation. The score should reflect the evaluation criteria specified in the user prompt.",
                        model=self.completion_model,
                        source=self.completion_source,
                        field="_ragprompt",
                        set_as=self.set_as)
