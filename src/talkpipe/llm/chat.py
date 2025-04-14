"""Classes for chatting with models from different sources.

Contains an abstract class for a chat model, as well as two 
concrete classes for chatting with models from Ollama.
"""

from typing import Optional, Iterable, Iterator
from abc import ABC, abstractmethod
import logging
from pydantic import BaseModel

from talkpipe.llm.config import TALKPIPE_MODEL_NAME, TALKPIPE_SOURCE
from talkpipe.util.data_manipulation import extract_property


from .config import getPromptAdapter, getPromptSources
from talkpipe.pipe.core import AbstractSegment
from talkpipe.chatterlang.registry import register_segment
from talkpipe.util.config import get_config

logger = logging.getLogger(__name__)

@register_segment("llmPrompt")
class LLMPrompt(AbstractSegment):
    """Interactive, optionally multi-turn, chat with an llm.
    
    Reads prompts from the input stream and emits responses from the llm.
    The model name and source can be specified in three different ways.  If
    explicitly included in the constructor, those values will be used.  If not,
    the values will be loaded from environment variables (TALKPIPE_default_model_name
    and TALKPIPE_default_source).  If those are not set, the values will be loaded
    from the configuration file (~/.talkpipe.toml).  If none of those are set, an 
    error will be raised.

    Args:
        name (str, optional): The name of the model to chat with. Defaults to None.
        source (ModelSource, optional): The source of the model. Defaults to None. Valid values are "openai" and "ollama."
        system_prompt (str, optional): The system prompt for the model. Defaults to "You are a helpful assistant.".
        multi_turn (bool, optional): Whether the chat is multi-turn. Defaults to True.
        pass_prompts (bool, optional): Whether to pass the prompts through to the output. Defaults to False.
        field (str, optional): The field in the input item containing the prompt. Defaults to None.
        append_as (str, optional): The field to append the response to. Defaults to None.
        temperature (float, optional): The temperature to use for the model. Defaults to 0.5.
        output_format (BaseModel, optional): A class used for guided generation. Defaults to None.
    """

    def __init__(
            self, 
            name: str = None, 
            source: str = None, 
            system_prompt: str = "You are a helpful assistant.", 
            multi_turn: bool = True,
            pass_prompts: bool = False,
            field: Optional[str] = None,
            append_as: Optional[str] = None,
            temperature: float = 0.5,
            output_format: BaseModel = None):
        super().__init__()
        logging.debug(f"Initializing LLMPrompt with name={name}, source={source}")
        cfg = get_config()
        name = name or cfg.get(TALKPIPE_MODEL_NAME, None)
        source = source or cfg.get(TALKPIPE_SOURCE, None)
        logging.debug(f"Resolved model name={name}, source={source}")
        
        if name is None or source is None:
            logging.error("Model name and source must be provided")
            raise ValueError("Model name and source must be provided, specified in the configuration file, or in environment variables.")

        if source not in getPromptSources():
            logging.error(f"Unknown source: {source}")
            raise ValueError(f"Unknown source: {source}")

        logging.debug(f"Creating chat model with name: {name}")
        self.chat = getPromptAdapter(source)(model_name=name, system_prompt=system_prompt, multi_turn=multi_turn, temperature=temperature, output_format=output_format)

        self.pass_prompts = pass_prompts
        self.field = field
        self.append_as = append_as

    def transform(self, input_iter: Iterable) -> Iterator:
        for item in input_iter:
            logger.debug(f"Processing input item: {item}")
            if self.field is not None:
                prompt = extract_property(item, self.field)
                logger.debug(f"Extracted prompt from field {self.field}: {prompt}")
            else:
                prompt = item
                logger.debug(f"Using item as prompt: {prompt}")
            
            if self.pass_prompts:
                logger.debug("Passing prompt through")
                yield prompt
            
            logger.debug(f"Executing chat with prompt: {prompt}")
            ans = self.chat.execute(str(prompt))
            logger.debug(f"Received response: {ans}")
            
            if self.append_as is not None:
                logger.debug(f"Appending response to field {self.append_as}")
                item[self.append_as] = ans
                yield item
            else:
                logger.debug("Yielding response directly")
                yield ans

class AbstractLLMGuidedGeneration(LLMPrompt):
    """Abstract class for LLM-guided generation segments.
    This class is used to create segments that generate output based on LLM responses.
    It is an abstract class and should not be used directly.
    Subclasses must implement the get_output_format method to specify the output format.
    Args:
        system_prompt (str): The system prompt for the LLM.
        name (str, optional): The name of the model to chat with. Defaults to None.
        source (str, optional): The source of the model. Defaults to None. Valid values are "openai" and "ollama."
        multi_turn (bool, optional): Whether the chat is multi-turn. Defaults to False.
        pass_prompts (bool, optional): Whether to pass the prompts through to the output. Defaults to False.
        field (str, optional): The field in the input item containing the prompt. Defaults to None.
        temperature (float, optional): The temperature to use for the model. Defaults to 0.5.
        append_as (str, optional): The field to append the response to. Defaults to None.
    """

    @staticmethod
    @abstractmethod
    def get_output_format() -> BaseModel:
        """Returns the output format for the segment. Must be implemented by subclasses."""
        pass

    def __init__(
            self, 
            system_prompt: str, 
            name: str = None, 
            source: str = None, 
            multi_turn: bool = False,
            pass_prompts: bool = False,
            field: Optional[str] = None,
            temperature: float = 0.5,
            append_as: Optional[str] = None):
        
        super().__init__(
            name, 
            source=source, 
            system_prompt=system_prompt, 
            multi_turn=multi_turn, 
            pass_prompts=pass_prompts, 
            field=field, 
            append_as=append_as, 
            temperature=temperature, 
            output_format=self.__class__.get_output_format())
        

@register_segment("llmScore")
class LlmScore(AbstractLLMGuidedGeneration):
    """For each piece of text read from the input stream, compute a score and an explanation for that score.
    
    The system prompt must be provided and should explain the range of the score (which must be 
    a range of integers) and the meaning of the score. For example, a system_prompt might be:
    
    <pre>Score the following text according to how relevant it is to canines, where 0 mean unrelated and 10 
    means highly related.</pre>

    See the LLMPrompt segment for more information on the other arguments.
    """

    class Score(BaseModel):
        explanation: str
        score: int

    @staticmethod
    def get_output_format() -> BaseModel:
        return LlmScore.Score
 

@register_segment("llmExtractTerms")
class LlmExtractTerms(AbstractLLMGuidedGeneration):
    """For each piece of text read from the input stream, extract terms from the text.
    
    The system prompt must be provided and should explain the nature of the terms. For 
    example, a system_prompt might be:
    
    <pre>Extract keywords from the following text.</pre>

    See the LLMPrompt segment for more information on the other arguments.
    """

    class Terms(BaseModel):
        explanation: str
        terms: list[str]

    @staticmethod
    def get_output_format() -> BaseModel:
        return LlmExtractTerms.Terms