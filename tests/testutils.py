from typing import Iterable, List
from unittest.mock import Mock 
import pytest
import os, re
from collections import namedtuple
from talkpipe.pipe.io import Prompt  # Import the Prompt source class
from talkpipe.util.config import get_config

@pytest.fixture
def monkeypatched_talkpipe_io_prompt(monkeypatch):
    """Fixture that patches Prompt.generate to yield custom inputs."""
    
    def _mock_prompt_responses(responses: List[str]):
        """Returns a function that mocks Prompt.generate with given responses."""
        def mock_generate(self) -> Iterable[str]:
            for response in responses:
                yield response
        monkeypatch.setattr(Prompt, "generate", mock_generate)

    return _mock_prompt_responses  # Return function to allow per-test customization

@pytest.fixture
def monkeypatched_env(monkeypatch):
    """Fixture to replace environment variables with a provided dictionary."""
    
    def _set_env(env_vars):

        for key in list(os.environ.keys()):
            monkeypatch.delenv(key, raising=False)

        """Replaces os.environ with given dictionary values."""
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)

    return _set_env  

@pytest.fixture
def patch_get_config(monkeypatch):
    monkeypatch.setattr("talkpipe.util.config.get_config", lambda *args, **kwargs: {})
    monkeypatch.setattr("talkpipe.llm.chat.get_config", lambda *args, **kwargs: {})
    
#############################################################################
# OpenAI Response Mocking
#############################################################################

# Define mock response structures
ChatCompletionMessage = namedtuple("ChatCompletionMessage", [
    "content", "refusal", "role", "audio", "function_call", "tool_calls"
])
Choice = namedtuple("Choice", ["finish_reason", "index", "logprobs", "message"])
CompletionUsage = namedtuple("CompletionUsage", [
    "completion_tokens", "prompt_tokens", "total_tokens",
    "completion_tokens_details", "prompt_tokens_details"
])
CompletionTokensDetails = namedtuple("CompletionTokensDetails", [
    "accepted_prediction_tokens", "audio_tokens", "reasoning_tokens",
    "rejected_prediction_tokens"
])
PromptTokensDetails = namedtuple("PromptTokensDetails", ["audio_tokens", "cached_tokens"])
ChatCompletion = namedtuple("ChatCompletion", [
    "id", "choices", "created", "model", "object", "service_tier",
    "system_fingerprint", "usage"
])

@pytest.fixture
def mock_openai_completion(monkeypatch):
    # Create mock client
    mock_client = Mock()
    
    # Create simplified mock response
    message = ChatCompletionMessage(
        content='Functions call themselves, \nLayers of logic entwined, \nEndless depth of code. ',
        role='assistant',
        refusal=False,
        audio=None,
        function_call=None,
        tool_calls=None
    )
    completion = ChatCompletion(
        id='chatcmpl-qwertyuiopasdfghjk',
        choices=[Choice(finish_reason='stop', index=0, message=message, logprobs=None)],
        created=1733594595,
        model='gpt-4o-mini-2024-07-18',
        object='chat.completion',
        service_tier='default',
        system_fingerprint='ab_cdefghijkl',
        usage=CompletionUsage(
            completion_tokens=20,
            prompt_tokens=26,
            total_tokens=46,
            completion_tokens_details=CompletionTokensDetails(0, 0, 0, 0),
            prompt_tokens_details=PromptTokensDetails(0, 0)
        )
    )
    
    # Directly attach the mock response to the client
    mock_client.beta.chat.completions.parse.return_value = completion
    
    # Patch the OpenAI constructor
    monkeypatch.setattr("openai.OpenAI", lambda: mock_client)
    
    return mock_client

is_url = lambda s: isinstance(s, str) and bool(re.match(r'^(https?|ftp)://[^\s/$.?#].[^\s]*$', s))

@pytest.fixture
def mock_requests_get_completion(monkeypatch):
    """Mock the requests.get method to return a custom response."""
    
    mock_client = Mock()

    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text or None

        def json(self):
            return self.json_data

    def mock_get(*args, **kwargs):
        if is_url(args[0]):
            # Simulate a successful response for a valid URL
            return MockResponse(status_code=200, text="<html><head><title>Mocked</title></head><body>The URL was: %s</body></html>" % args[0])
        else:
            # Simulate a failure for non-URL inputs
            return MockResponse(status_code=404, text=None)
    
    mock_client.get.return_value = mock_get

    monkeypatch.setattr("requests.get", mock_get)
    return mock_get


