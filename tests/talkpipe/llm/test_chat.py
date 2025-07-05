from pydantic import BaseModel
import pytest
from talkpipe.llm.prompt_adapters import OllamaPromptAdapter, OpenAIPromptAdapter
from testutils import monkeypatched_env, patch_get_config
from talkpipe.util import config

from talkpipe.llm.chat import LLMPrompt, LlmScore, LlmExtractTerms
from talkpipe.chatterlang import compiler


def test_invalid_source(monkeypatched_env, patch_get_config):

    monkeypatched_env({})

    assert config.get_config() == {}

    with pytest.raises(ValueError):
        LLMPrompt(name="llama3.2", source="fake", temperature=0.0)

    with pytest.raises(ValueError):
        LLMPrompt(name=None, source="ollama", temperature=0.0)

    with pytest.raises(ValueError):
        LLMPrompt(name="llama3.2", source=None, temperature=0.0)

def test_is_available(requires_ollama):
    chat = OllamaPromptAdapter("llama3.2", temperature=0.0)
    assert chat.is_available() is True

    chat = OpenAIPromptAdapter("gpt-4.1-nano", temperature=0.0)
    assert chat.is_available() is True

def test_ollamachat(requires_ollama):
    chat = OllamaPromptAdapter("llama3.2", temperature=0.0)
    assert chat.model_name == "llama3.2"
    assert chat.source == "ollama"
    ans = chat.execute("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    ans = chat.execute("I just told you my first name?  What is it?")
    assert "inigo" in ans.lower()

    chat = OllamaPromptAdapter("llama3.2", multi_turn=False, temperature=0.0)
    assert chat.model_name == "llama3.2"
    assert chat.source == "ollama"
    ans = chat.execute("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    assert len(ans) > 0
    ans = chat.execute("I just told you my first name?  What is it?")
    assert "inigo" not in ans.lower()


def test_openai_chat(requires_openai):
    chat = OpenAIPromptAdapter("gpt-4.1-nano", temperature=0.0)
    assert chat.model_name == "gpt-4.1-nano"
    assert chat.source == "openai"
    ans = chat.execute("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    ans = chat.execute("I just told you my first name?  What is it?")
    assert "inigo" in ans.lower()

class TestOpenAIChatGuidedGeneration(BaseModel):
    """Test class for OpenAI guided generation."""
    response: str
    explanation: str

def test_openai_chat_guided_generation(requires_openai):
    system_prompt = """
    "You are a helpful assistant.  Your task is to answer the user's question and provide an explanation for your answer."
    """

    chat = OpenAIPromptAdapter("gpt-4.1-nano", system_prompt=system_prompt, temperature=0.0, output_format=TestOpenAIChatGuidedGeneration)
    assert chat.model_name == "gpt-4.1-nano"
    assert chat.source == "openai"

    response = chat.execute("What is the capital of France?")
    assert isinstance(response, TestOpenAIChatGuidedGeneration)
    assert "paris" in response.response.lower() 
    assert len(response.explanation) > 0

    # Test with a different question
    response = chat.execute("What is the largest planet in our solar system?")
    assert isinstance(response, TestOpenAIChatGuidedGeneration)
    assert "jupiter" in response.response.lower()
    assert len(response.explanation) > 0

def test_chat(requires_ollama):
    chat = LLMPrompt(name="llama3.2", source="ollama", temperature=0.0)

    # There is an interesting issue here.  You have to deplete the generator before you can get the next response.
    assert isinstance(chat.chat, OllamaPromptAdapter)    
    response = next(chat(["Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die."]))
    response = next(chat(["I just told you my first name?  What is it?"]))
    assert "inigo" in response.lower()

    chat = LLMPrompt(name="llama3.2", source="ollama", multi_turn=False, temperature=0.0)
    assert isinstance(chat.chat, OllamaPromptAdapter)
    chat = chat.asFunction(single_in=True, single_out=True)
    response = chat("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    assert len(response) > 0
    response = chat("I just told you my first name?  What is it?")
    assert "Inigo" not in response.lower()

    chat = compiler.compile('llmPrompt[name="llama3.1", source="ollama", multi_turn=True, temperature=0.0]').asFunction(single_in=True, single_out=True)
    response = chat("Hello.  My name is Inigo Montoya.  You killed my father.  Prepare to die.")
    assert len(response) > 0
    response = chat("I just told you my first name?  What is it?")
    assert "inigo" in response.lower()

def test_chat_append_as(requires_ollama):
    chat = LLMPrompt(name="llama3.2", source="ollama", append_as="response", temperature=0.0)
    chat = chat.asFunction(single_in=True, single_out=True)
    response = chat({"message": "Hello.  My name is Inigo Montoya.  You killed my father."})
    assert isinstance(response, dict)
    assert "response" in response
    assert "message" in response

    chat = LLMPrompt(name="llama3.2", source="ollama", temperature=0.0)
    chat = chat.asFunction(single_in=True, single_out=True)
    response = chat("Hello.  My name is Inigo Montoya.  You killed my father.")
    assert isinstance(response, str)

def test_chat_property(requires_ollama):
    chat = LLMPrompt(name="llama3.2", source="ollama", field="message")
    chat = chat.asFunction(single_in=True, single_out=True)
    response = chat({"message": "Say hello", "directive": "Reply in all caps"})
    assert isinstance(response, str)
    assert "HELLO" not in response

    chat = LLMPrompt(name="llama3.2", source="ollama")
    chat = chat.asFunction(single_in=True, single_out=True)
    response = chat({"message": "Say hello", "directive": "Reply in all caps"})
    assert isinstance(response, str)
    assert "HELLO" in response

class AnAnswer(BaseModel):
    ans: int

def test_chat_formatted(requires_ollama):
    chat = LLMPrompt(name="llama3.2", source="ollama", output_format=AnAnswer)
    chat = chat.asFunction(single_in=True, single_out=True)
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

    llmscore = LlmScore(system_prompt=system_prompt, multi_turn=False, temperature=0.0)
    llmscore = llmscore.asFunction(single_in=True, single_out=True)
    response = llmscore(dog_text)
    assert isinstance(response.score, int)
    assert response.score > 7
    assert isinstance(response.explanation, str)
    assert len(response.explanation) > 0

    response = llmscore(cat_text)
    assert response.score < 3

    llmscore = LlmScore(system_prompt=system_prompt, field="assertion", append_as="canine_similarity", temperature=0.0)
    llmscore = llmscore.asFunction(single_in=True, single_out=True)
    response = llmscore({"assertion":dog_text})
    assert isinstance(response, dict)
    assert response["canine_similarity"].score > 7
    assert response["canine_similarity"].explanation is not None

    response = llmscore({"assertion":cat_text})
    assert response["canine_similarity"].score < 3

def test_llmextractterms(requires_ollama):
    system_prompt="""Extract the names from the following text in lower case."""
    llmextractterms = LlmExtractTerms(system_prompt=system_prompt, multi_turn=False, temperature=0.0)
    llmextractterms = llmextractterms.asFunction(single_in=True, single_out=True)
    response = llmextractterms("Bob went to the coffee shop to see Sally.")
    assert isinstance(response, LlmExtractTerms.Terms)
    assert len(response.terms) > 0
    assert isinstance(response.explanation, str)
    assert len(response.explanation) > 0
    assert isinstance(response.terms, list)
    assert len(response.terms) > 0
    assert "bob" in response.terms
    assert "sally" in response.terms