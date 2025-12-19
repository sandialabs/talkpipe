"""Classes for chatting with models from different sources.

Contains an abstract class for a chat model, as well as two 
concrete classes for chatting with models from Ollama.
"""

from typing import Optional, Iterable, Iterator, Annotated
from abc import ABC, abstractmethod
import logging
from pydantic import BaseModel

from talkpipe.util.constants import TALKPIPE_MODEL_NAME, TALKPIPE_SOURCE
from talkpipe.util.data_manipulation import extract_property, assign_property


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

    Currently supported sources are "ollama," "openai," and "anthropic."  If 
    you specify "ollama," you can optionally set the OLLAMA_SERVER_URL environment
    variable or configuration value to point to a different server.  By default,
    ollama assumes localhost.
    """

    def __init__(
            self,
            model: Annotated[Optional[str], "The name of the model to chat with"] = None,
            source: Annotated[Optional[str], "The source of the model (openai or ollama)"] = None,
            system_prompt: Annotated[str, "The system prompt for the model"] = "You are a helpful assistant.",
            multi_turn: Annotated[bool, "Whether the chat is multi-turn"] = True,
            pass_prompts: Annotated[bool, "Whether to pass the prompts through to the output"] = False,
            field: Annotated[Optional[str], "The field in the input item containing the prompt"] = None,
            set_as: Annotated[Optional[str], "The field to append the response to"] = None,
            temperature: Annotated[Optional[float], "The temperature to use for the model"] = None,
            output_format: Annotated[Optional[BaseModel], "A class used for guided generation"] = None,
            role_map: Annotated[Optional[str], "Initial conversation context as 'role:message,role:message'"] = None):
        super().__init__()
        logging.debug(f"Initializing LLMPrompt with name={model}, source={source}")
        cfg = get_config()
        model = model or cfg.get(TALKPIPE_MODEL_NAME, None)
        source = source or cfg.get(TALKPIPE_SOURCE, None)
        logging.debug(f"Resolved model name={model}, source={source}")

        if model is None or source is None:
            logging.error("Model name and source must be provided")
            raise ValueError("Model name and source must be provided, specified in the configuration file, or in environment variables.")

        if source not in getPromptSources():
            logging.error(f"Unknown source: {source}")
            raise ValueError(f"Unknown source: {source}")

        logging.debug(f"Creating chat model with name: {model}")
        self.chat = getPromptAdapter(source)(model=model, system_prompt=system_prompt, multi_turn=multi_turn, temperature=temperature, output_format=output_format, role_map=role_map)

        self.pass_prompts = pass_prompts
        self.field = field
        self.set_as = set_as

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
            
            if self.set_as is not None:
                logger.debug(f"Appending response to field {self.set_as}")
                assign_property(item, self.set_as, ans)
                yield item
            else:
                logger.debug("Yielding response directly")
                yield ans

class AbstractLLMGuidedGeneration(LLMPrompt):
    """Abstract class for LLM-guided generation segments.
    This class is used to create segments that generate output based on LLM responses.
    It is an abstract class and should not be used directly.
    Subclasses must implement the get_output_format method to specify the output format.
    """

    @staticmethod
    @abstractmethod
    def get_output_format() -> BaseModel:
        """Returns the output format for the segment. Must be implemented by subclasses."""
        pass

    def __init__(
            self,
            system_prompt: Annotated[str, "The system prompt for the LLM"],
            model: Annotated[Optional[str], "The name of the model to chat with"] = None,
            source: Annotated[Optional[str], "The source of the model (openai or ollama)"] = None,
            multi_turn: Annotated[bool, "Whether the chat is multi-turn"] = False,
            pass_prompts: Annotated[bool, "Whether to pass the prompts through to the output"] = False,
            field: Annotated[Optional[str], "The field in the input item containing the prompt"] = None,
            temperature: Annotated[Optional[float], "The temperature to use for the model"] = None,
            set_as: Annotated[Optional[str], "The field to append the response to"] = None,
            role_map: Annotated[Optional[str], "Initial conversation context as 'role:message,role:message'"] = None):

        super().__init__(
            model,
            source=source,
            system_prompt=system_prompt,
            multi_turn=multi_turn,
            pass_prompts=pass_prompts,
            field=field,
            set_as=set_as,
            temperature=temperature,
            output_format=self.__class__.get_output_format(),
            role_map=role_map)
        

@register_segment("llmScore")
class LlmScore(AbstractLLMGuidedGeneration):
    """
    Compute an integer relevance (or quality) score and a natural‑language explanation
    for each prompt using an LLM.
    Overview
    --------
    LlmScore is a thin specialization of AbstractLLMGuidedGeneration that:
    1. Accepts arbitrary text segments (e.g., from a streaming source or an iterator).
    2. For each segment, asks the LLM (guided by your system prompt) to produce:
        - score: An integer within a range you define in the system prompt.
        - explanation: A short justification describing why that score was assigned.
    3. Validates / structures the model response into an instance of LlmScore.Score
        (a pydantic model with fields `score: int`, `explanation: str`).
    You MUST supply a system prompt that clearly defines:
    - The scoring scale (integer range, e.g., 0–10 or 1–5).
    - The semantics of low / high values.
    - Any domain‑specific evaluation criteria.

    Intended Use Cases
    ------------------
    - Content relevance scoring (e.g., "How related is this passage to canines?").
    - Quality, safety, or policy compliance triage.
    - Lightweight ranking signals ahead of deeper analysis.
    - Real‑time streaming evaluation of incoming documents or chat messages.
    
    Parameters (inherited / expected)
    ---------------------------------
    While this class adds no new constructor arguments beyond those of
    AbstractLLMGuidedGeneration, the following (typical) parameters of the base
    class are especially relevant here (names may vary depending on your concrete
    implementation):
    - system_prompt (str, required):
         A carefully crafted instruction that:
            * Defines the integer scoring range (e.g., 0–10).
            * Explains the meaning of endpoints and (optionally) intermediate values.
            * Requests a JSON (or structured) output containing fields:
                 - "score": integer
                 - "explanation": brief textual rationale
         Example:
            "You are a scoring assistant. Score the supplied text for how
             relevant it is to canines on a 0–10 scale (0 = unrelated, 10 = highly
             specific and directly about canines). Return JSON with keys
             'score' (int) and 'explanation' (string). Be concise."
    - model:
         Name of the LLM model to use.
    - source:
         The input source for the text segments (e.g., "ollama" or "openai").
    - pass_prompts (bool, optional):
         Whether to include the original prompts in the output.
    - multi_turn (bool, optional):
         Whether the interaction is part of a multi-turn dialogue.
    - field (str, optional):
         The specific field serve as the prompt (e.g., "content", "style").
    - temperature (float, optional):
         Sampling temperature; often set low (e.g., 0.0–0.3) to encourage
         deterministic, reproducible scoring.
    - set_as (str, optional):
         If specified, the output will be appended as this field in the
         final response.

    Data Model
    ----------
    class Score:
         score (int):
              The integer score within the scale you defined in the system prompt.
              Always validate that returned values fall in-range; if not, consider
              clamping, rejecting, or re‑prompting.
         explanation (str):
              Concise justification of why the score was chosen. Encourage the model
              (via the prompt) to reference explicit criteria, avoid hallucinated
              facts, and keep it short (e.g., <= 2 sentences) for efficiency.

    Method Notes
    ------------
    get_output_format():
         Returns the Pydantic model (LlmScore.Score) that defines the expected
         structure of each LLM response. This is used by the base class to coerce
         raw model output into typed objects.

    Prompt Engineering Tips
    -----------------------
    - Explicitly enumerate the allowed integer values (e.g., "Allowed scores: 0,1,2,...,10").
    - Require a single JSON object with only the two keys to reduce parsing failures.
    - Instruct the model NOT to include extra commentary outside JSON (or use a
      structured output feature if the provider supports it).
    - For consistency, set temperature close to 0 when subjective diversity is
      not desired.

    Performance Considerations
    --------------------------
    - Batch scoring: If your base class supports batching, you can group multiple
      text segments per request to reduce overhead (ensure the prompt clarifies
      batched output format).
    - Streaming input: Feed contiguous chunks; consider normalizing whitespace
      and truncating overlong inputs to control token costs.
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
        terms: list[str]

    @staticmethod
    def get_output_format() -> BaseModel:
        return LlmExtractTerms.Terms

@register_segment("llmBinaryAnswer")
class LlmBinaryAnswer(AbstractLLMGuidedGeneration):
    """For each piece of text read from the input stream, generate a binary answer (yes/no).
    The system prompt must be provided and should explain the nature of the question.

    For example, the system prompt might be:

    <pre>Is the following text positive or negative?</pre>

    See the LLMPrompt segment for more information on the other arguments.
    """

    class Answer(BaseModel):
        explanation: str
        answer: bool

    @staticmethod
    def get_output_format() -> BaseModel:
        return LlmBinaryAnswer.Answer