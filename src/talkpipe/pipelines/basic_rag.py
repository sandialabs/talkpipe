""" Basic RAG pipeline implementation """
from typing import Annotated, List, Union, Any
import logging
from talkpipe import AbstractSegment, AbstractFieldSegment, register_segment
from talkpipe.search.abstract import SearchResult
from talkpipe.llm.chat import LlmScore, LLMPrompt
from talkpipe.util.data_manipulation import extract_property
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
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"],
                 background_field: Annotated[str, "Field containing background items"],
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
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
                item[self.set_as] = prompt
                yield item
            else:
                yield prompt


@register_segment("ragToText")
class RAGToText(AbstractSegment):
    """ Convenience segment that runs a RAG pipeline from search to prompt creation to LLM completion.
    """
    
    def __init__(self,
                 embedding_model: Annotated[str, "Embedding model to use"],
                 embedding_source: Annotated[str, "Source of text to embed"],
                 completion_model: Annotated[str, "LLM model to use for completion"],
                 completion_source: Annotated[str, "Source of prompt for completion"],
                 path: Annotated[str, "Path to the LanceDB database"],
                 content_field: Annotated[Any, "Field to evaluate relevance on"],
                 prompt_directive: Annotated[str, "Directive to guide the evaluation"] = "Respond to the provided content based on the background information. If the background does not contain relevant information, respond with 'No relevant information found.'",
                 set_as: Annotated[str, "The field to set/append the result as."] = None,
                 limit: Annotated[int, "Number of search results to retrieve"] = 10,
                 read_consistency_interval: Annotated[int, "Read consistency interval in seconds"] = 10):

        super().__init__()
        self.embedding_model = embedding_model
        self.embedding_source = embedding_source
        self.path = path
        self.completion_model = completion_model
        self.completion_source = completion_source
        self.prompt_directive = prompt_directive
        self.content_field = content_field
        self.set_as = set_as
        self.limit = limit
        self.read_consistency_interval = read_consistency_interval

        self.pipeline = SearchVectorDatabaseSegment(embedding_model=self.embedding_model,
                                                    embedding_source=self.embedding_source,
                                                    path=self.path,
                                                    set_as="_background",
                                                    limit=self.limit,
                                                    query_field=self.content_field,
                                                    read_consistency_interval=self.read_consistency_interval) | \
                        ConstructRAGPrompt(prompt_directive=self.prompt_directive,
                                            background_field="_background",
                                            content_field=self.content_field,
                                            set_as="_ragprompt") | \
                        LLMPrompt(model=self.completion_model,
                                  source=self.completion_source,
                                  field="_ragprompt",
                                  set_as=self.set_as)
        
    def transform(self, input_iter):
        yield from self.pipeline(input_iter)