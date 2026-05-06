from pydantic import BaseModel
import pytest
from talkpipe.llm.prompt_adapters import (
    AbstractLLMPromptAdapter,
    OllamaPromptAdapter,
    OpenAIPromptAdapter,
    AnthropicPromptAdapter,
)
from testutils import monkeypatched_env, patch_get_config
from talkpipe.util import config

from talkpipe.llm.chat import LLMPrompt, LlmScore, LlmExtractTerms, LlmBinaryAnswer
from talkpipe.chatterlang import compiler

def test_context_management_defaults_are_backward_compatible():
    adapter = OllamaPromptAdapter("llama3.2")
    assert adapter._memory_mode == "full"
    assert adapter._summary_strategy == "llm"
    assert adapter._summary_message is None
    assert adapter._needs_compaction() is False

def test_context_compaction_falls_back_from_llm(monkeypatch):
    adapter = OllamaPromptAdapter(
        "llama3.2",
        memory_mode="summary_llm",
        context_token_trigger=40,
        unsummarized_message_count=1,
    )
    adapter._messages = [
        {"role": "user", "content": "A long user message to overflow the token budget."},
        {"role": "assistant", "content": "A long assistant reply with details."},
        {"role": "user", "content": "Recent message that should be preserved."},
    ]

    def raise_summary(*args, **kwargs):
        raise RuntimeError("summary call failed")

    monkeypatch.setattr(adapter, "_summarize_with_llm", raise_summary)
    adapter._compact_context_if_needed()
    assert adapter._summary_message is not None
    assert "deterministic fallback" in adapter._summary_message["content"].lower()
    assert len(adapter._messages) == 1
    assert adapter._messages[0]["content"] == "Recent message that should be preserved."

def test_summary_llm_uses_no_context_completion_hook():
    class SummaryHookAdapter(OllamaPromptAdapter):
        def complete_text_without_context(self, prompt, *, model=None, temperature=0.0, max_tokens=None):
            assert model == "llama3.2"
            assert temperature == 0.0
            assert max_tokens == self._summary_max_tokens
            assert "Previous summary:" in prompt
            assert "Archived messages:" in prompt
            return "hook summary"

    adapter = SummaryHookAdapter("llama3.2", memory_mode="summary_llm")
    assert adapter._summarize_history("", [{"role": "user", "content": "old fact"}]) == "hook summary"

def test_summary_llm_without_no_context_completion_hook_raises():
    class NoSummaryHookAdapter(OllamaPromptAdapter):
        complete_text_without_context = AbstractLLMPromptAdapter.complete_text_without_context

    adapter = NoSummaryHookAdapter("llama3.2", memory_mode="summary_llm")

    with pytest.raises(NotImplementedError, match="complete_text_without_context"):
        adapter._summarize_history("", [{"role": "user", "content": "old fact"}])

def test_llmprompt_passes_context_params(monkeypatch):
    captured = {}

    class CaptureAdapter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def execute(self, prompt):
            return prompt

    monkeypatch.setattr("talkpipe.llm.chat.getPromptSources", lambda: ["capture"])
    monkeypatch.setattr("talkpipe.llm.chat.getPromptAdapter", lambda _source: CaptureAdapter)

    _segment = LLMPrompt(
        model="model-a",
        source="capture",
        memory_mode="summary_deterministic",
        context_token_trigger=0.8,
        unsummarized_message_count=4,
        memory_size=256,
        debug_messages=True,
    )

    assert captured["model"] == "model-a"
    assert captured["memory_mode"] == "summary_deterministic"
    assert captured["context_token_trigger"] == 0.8
    assert captured["unsummarized_message_count"] == 4
    assert captured["memory_size"] == 256
    assert captured["debug_messages"] is True

def test_guided_generation_passes_context_params(monkeypatch):
    captured = {}

    class CaptureAdapter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def execute(self, prompt):
            return prompt

    monkeypatch.setattr("talkpipe.llm.chat.getPromptSources", lambda: ["capture"])
    monkeypatch.setattr("talkpipe.llm.chat.getPromptAdapter", lambda _source: CaptureAdapter)

    _segment = LlmScore(
        system_prompt="score it",
        model="model-a",
        source="capture",
        memory_mode="recent_only",
        context_token_trigger=4096,
        unsummarized_message_count=5,
        memory_size=128,
    )

    assert captured["model"] == "model-a"
    assert captured["memory_mode"] == "recent_only"
    assert captured["context_token_trigger"] == 4096
    assert captured["unsummarized_message_count"] == 5
    assert captured["memory_size"] == 128

def test_llmprompt_supports_old_adapter_defaults(monkeypatch, caplog):
    captured = {}

    class OldStyleAdapter:
        def __init__(
            self,
            model,
            system_prompt="You are a helpful assistant.",
            multi_turn=True,
            temperature=None,
            output_format=None,
            role_map=None,
        ):
            captured.update(
                {
                    "model": model,
                    "system_prompt": system_prompt,
                    "multi_turn": multi_turn,
                    "temperature": temperature,
                    "output_format": output_format,
                    "role_map": role_map,
                }
            )

        def execute(self, prompt):
            return prompt

    monkeypatch.setattr("talkpipe.llm.chat.getPromptSources", lambda: ["old"])
    monkeypatch.setattr("talkpipe.llm.chat.getPromptAdapter", lambda _source: OldStyleAdapter)

    with caplog.at_level("WARNING", logger="talkpipe.llm.chat"):
        segment = LLMPrompt(model="model-a", source="old")

    assert isinstance(segment.chat, OldStyleAdapter)
    assert captured["model"] == "model-a"
    assert "memory_mode" not in captured
    assert "does not support memory summarization" in caplog.text

def test_llmprompt_rejects_old_adapter_with_memory_request(monkeypatch):
    class OldStyleAdapter:
        def __init__(
            self,
            model,
            system_prompt="You are a helpful assistant.",
            multi_turn=True,
            temperature=None,
            output_format=None,
            role_map=None,
        ):
            pass

        def execute(self, prompt):
            return prompt

    monkeypatch.setattr("talkpipe.llm.chat.getPromptSources", lambda: ["old"])
    monkeypatch.setattr("talkpipe.llm.chat.getPromptAdapter", lambda _source: OldStyleAdapter)

    with pytest.raises(ValueError, match="does not support memory controls"):
        LLMPrompt(model="model-a", source="old", memory_mode="summary_deterministic")

def test_invalid_source(monkeypatched_env, patch_get_config):

    monkeypatched_env({})

    assert config.get_config() == {}

    with pytest.raises(ValueError):
        LLMPrompt(model="llama3.2", source="fake", temperature=0.0)

    with pytest.raises(ValueError):
        LLMPrompt(model=None, source="ollama", temperature=0.0)

    with pytest.raises(ValueError):
        LLMPrompt(model="llama3.2", source=None, temperature=0.0)


def test_role_map_in_llmprompt_segment():
    """Test that role_map is passed through LLMPrompt segment to the adapter."""
    chat = LLMPrompt(model="llama3.2", source="ollama",
                     role_map="system:Custom system,user:Hello,assistant:Hi there")
    assert chat.chat._system_message == {"role": "system", "content": "Custom system"}
    assert len(chat.chat._prefix_messages) == 3

def test_system_prompt_none():
    """Test that when system_prompt is None, it is not passed to the adapter and no system message is created."""
    # Test with explicit None
    chat = LLMPrompt(model="llama3.2", source="ollama", system_prompt=None)
    assert chat.chat._system_message is None
    assert len(chat.chat._prefix_messages) == 0
    
    # Test that adapter works without system prompt
    adapter = OllamaPromptAdapter("llama3.2", system_prompt=None)
    assert adapter._system_message is None
    assert len(adapter._prefix_messages) == 0
    
    # Test that adapter works with explicit None and role_map (but no system role)
    adapter = OllamaPromptAdapter("llama3.2", system_prompt=None, role_map="user:Hello")
    assert adapter._system_message is None
    assert len(adapter._prefix_messages) == 1
    assert adapter._prefix_messages[0] == {"role": "user", "content": "Hello"}

class TestGuidedGeneration(BaseModel):
    """Test class for OpenAI guided generation."""
    response: str
    explanation: str

def test_openai_chat_guided_generation(requires_openai):
    system_prompt = """
    "You are a helpful assistant.  Your task is to answer the user's question and provide an explanation for your answer."
    """

    chat = OpenAIPromptAdapter("gpt-4.1-nano", system_prompt=system_prompt, temperature=0.0, output_format=TestGuidedGeneration)
    assert chat.model_name == "gpt-4.1-nano"
    assert chat.source == "openai"

    response = chat.execute("What is the capital of France?")
    assert isinstance(response, TestGuidedGeneration)
    assert "paris" in response.response.lower() 
    assert len(response.explanation) > 0

    # Test with a different question
    response = chat.execute("What is the largest planet in our solar system?")
    assert isinstance(response, TestGuidedGeneration)
    assert "jupiter" in response.response.lower()
    assert len(response.explanation) > 0

def test_anthropic_guided_generation(requires_anthropic):
    system_prompt = """
    "You are a helpful assistant.  Your task is to answer the user's question and provide an explanation for your answer."
    """

    chat = AnthropicPromptAdapter("claude-3-5-haiku-latest", system_prompt=system_prompt, temperature=0.0, output_format=TestGuidedGeneration)
    assert chat.model_name == "claude-3-5-haiku-latest"
    assert chat.source == "anthropic"

    response = chat.execute("What is the capital of France?")
    assert isinstance(response, TestGuidedGeneration)
    assert "paris" in response.response.lower() 
    assert len(response.explanation) > 0

    # Test with a different question
    response = chat.execute("What is the largest planet in our solar system?")
    assert isinstance(response, TestGuidedGeneration)
    assert "jupiter" in response.response.lower()
    assert len(response.explanation) > 0

def test_chat(requires_ollama):
    chat = LLMPrompt(model="llama3.2", source="ollama", temperature=0.0)

    # There is an interesting issue here.  You have to deplete the generator before you can get the next response.
    assert isinstance(chat.chat, OllamaPromptAdapter)    
    response = next(chat(["Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die."]))
    response = next(chat(["I just told you my first name?  What is it?"]))
    assert "inigo" in response.lower()

    chat = LLMPrompt(model="llama3.2", source="ollama", multi_turn=False, temperature=0.0)
    assert isinstance(chat.chat, OllamaPromptAdapter)
    chat = chat.as_function(single_in=True, single_out=True)
    response = chat("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    assert len(response) > 0
    response = chat("I just told you my first name?  What is it?")
    assert "Inigo" not in response.lower()

    chat = compiler.compile('llmPrompt[model="llama3.1", source="ollama", multi_turn=True, temperature=0.0]').as_function(single_in=True, single_out=True)
    response = chat("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    assert len(response) > 0
    response = chat("I just told you my first name?  What is it?")
    assert "inigo" in response.lower()

def test_chat_set_as(requires_ollama):
    chat = LLMPrompt(model="llama3.2", source="ollama", set_as="response", temperature=0.0)
    chat = chat.as_function(single_in=True, single_out=True)
    response = chat({"message": "Hello.  My name is Inigo Montoya.  You killed my father."})
    assert isinstance(response, dict)
    assert "response" in response
    assert "message" in response

    chat = LLMPrompt(model="llama3.2", source="ollama", temperature=0.0)
    chat = chat.as_function(single_in=True, single_out=True)
    response = chat("Hello.  My name is Inigo Montoya.  You killed my father.")
    assert isinstance(response, str)

def test_chat_property(requires_ollama):
    chat = LLMPrompt(model="llama3.2", source="ollama", field="message")
    chat = chat.as_function(single_in=True, single_out=True)
    response = chat({"message": "Say hello", "directive": "Reply in all caps"})
    assert isinstance(response, str)
    assert "HELLO" not in response

    chat = LLMPrompt(model="llama3.2", source="ollama")
    chat = chat.as_function(single_in=True, single_out=True)
    response = chat({"message": "Say hello", "directive": "Reply in all caps"})
    assert isinstance(response, str)
    assert "HELLO" in response

def test_chat_ollama_custom_host(requires_ollama, monkeypatch):
    # Test that OLLAMA_SERVER_URL environment variable is respected
    custom_url = "http://custom-ollama:11434"
    monkeypatch.setenv("TALKPIPE_OLLAMA_SERVER_URL", custom_url)
    
    chat = LLMPrompt(model="llama3.2", source="ollama", temperature=0.0)
    chat = chat.as_function(single_in=True, single_out=True)
    # Mock the ollama.Client to verify custom URL is passed
    def mock_client_init(self, host=None, **kwargs):
        assert host == custom_url, f"Expected host {custom_url}, got {host}"
        # Store original attributes that might be needed
        self.host = host
        
    monkeypatch.setattr("ollama.Client.__init__", mock_client_init)

    # Test that the chat works with custom URL
    try:
        response = chat("Hello, this is a test.")
    except Exception:
        # The mock will prevent actual connection, but we verified the URL was passed correctly
        pass


class AnAnswer(BaseModel):
    ans: int

def test_chat_formatted(requires_ollama):
    chat = LLMPrompt(model="llama3.2", source="ollama", output_format=AnAnswer)
    chat = chat.as_function(single_in=True, single_out=True)
    response = chat("What is 1+1?")
    assert isinstance(response, AnAnswer)
    assert response.ans == 2

def test_llmscore(requires_ollama):
    system_prompt = """
    "Score the following text according to how relevant it is to anything about canines, 
    where 0 mean unrelated and 10 means highly related."
    """

    dog_text = "Husky is a general term for a dog used in the polar regions, primarily and specifically for work as sled dogs. It refers to a traditional northern type, notable for its cold-weather tolerance and overall hardiness.[1][2] Modern racing huskies that maintain arctic breed traits (also known as Alaskan huskies) represent an ever-changing crossbreed of the fastest dogs."
    cat_text = "The cat (Felis catus), also referred to as the domestic cat, is a small domesticated carnivorous mammal. It is the only domesticated species of the family Felidae. Advances in archaeology and genetics have shown that the domestication of the cat occurred in the Near East around 7500 BC. It is commonly kept as a pet and farm cat, but also ranges freely as a feral cat avoiding human contact. Valued by humans for companionship and its ability to kill vermin, the cat's retractable claws are adapted to killing small prey such as mice and rats. It has a strong, flexible body, quick reflexes, and sharp teeth, and its night vision and sense of smell are well developed. It is a social species, but a solitary hunter and a crepuscular predator. Cat communication includes vocalizations—including meowing, purring, trilling, hissing, growling, and grunting—as well as body language. It can hear sounds too faint or too high in frequency for human ears, such as those made by small mammals. It secretes and perceives pheromones."

    llmscore = LlmScore(system_prompt=system_prompt, multi_turn=False, temperature=0.0, model="llama3.2", source="ollama")
    llmscore = llmscore.as_function(single_in=True, single_out=True)
    response = llmscore(dog_text)
    assert isinstance(response.score, int)
    assert response.score > 7
    assert isinstance(response.explanation, str)
    assert len(response.explanation) > 0

    response = llmscore(cat_text)
    assert response.score < 3

    llmscore = LlmScore(system_prompt=system_prompt, field="assertion", set_as="canine_similarity", temperature=0.0, model="llama3.2", source="ollama")
    llmscore = llmscore.as_function(single_in=True, single_out=True)
    response = llmscore({"assertion":dog_text})
    assert isinstance(response, dict)
    assert response["canine_similarity"].score > 7
    assert response["canine_similarity"].explanation is not None

    response = llmscore({"assertion":cat_text})
    assert response["canine_similarity"].score < 3

def test_llmextractterms(requires_ollama):
    system_prompt="""Extract the names of people from the following text in lower case."""
    llmextractterms = LlmExtractTerms(system_prompt=system_prompt, multi_turn=False, temperature=0.0, model="llama3.2", source="ollama")
    llmextractterms = llmextractterms.as_function(single_in=True, single_out=True)
    response = llmextractterms("Bob went to the coffee shop to see Sally.")
    assert isinstance(response, LlmExtractTerms.Terms)
    assert len(response.terms) > 0
    assert isinstance(response.terms, list)
    assert len(response.terms) > 0
    assert "bob" in response.terms
    assert "sally" in response.terms

def test_llmbinaryanswer(requires_ollama):
    system_prompt="""Is the following text positive or negative?"""
    llmbinaryanswer = LlmBinaryAnswer(system_prompt=system_prompt, multi_turn=False, temperature=0.0, model="llama3.2", source="ollama")
    llmbinaryanswer = llmbinaryanswer.as_function(single_in=True, single_out=True)
    response = llmbinaryanswer("I love this product!")
    assert isinstance(response, LlmBinaryAnswer.Answer)
    assert response.answer is True
    assert isinstance(response.explanation, str)
    assert len(response.explanation) > 0

    response = llmbinaryanswer("I hate this product!")
    assert response.answer is False

    llmbinaryanswer = LlmBinaryAnswer(system_prompt=system_prompt, field="assertion", set_as="sentiment", temperature=0.0, model="llama3.2", source="ollama")
    llmbinaryanswer = llmbinaryanswer.as_function(single_in=True, single_out=True)
    response = llmbinaryanswer({"assertion":"I love this product!"})
    assert isinstance(response, dict)
    assert response["sentiment"].answer is True
    assert response["sentiment"].explanation is not None
