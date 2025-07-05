"""PyTest configuration for MongoDB tests.

Provides fixtures for both real MongoDB testing and mocked testing.
"""

import pytest
import logging
import os
from talkpipe.llm.prompt_adapters import OllamaPromptAdapter, OpenAIPromptAdapter
from pymongo import MongoClient
import mongomock
import unittest.mock

logger = logging.getLogger(__name__)

# Constants for testing
TEST_DB_NAME = "talkpipe_test_db"
TEST_COLLECTION = "test_collection"
TEST_CONNECTION_STRING = os.environ.get("TALKPIPE_mongo_connection_string")

def pytest_configure(config):
    """Check if the test is running online."""
    # Initialize config attributes for service availability
    config.is_ollama_available = False
    config.is_mongodb_available = False
    config.is_openai_available = False
    
    # Check if Ollama is available
    ollama_adapter = OllamaPromptAdapter("llama3.2", temperature=0.0)
    if ollama_adapter.is_available():
        config.is_ollama_available = True
        logger.warning("Ollama is available.")
    else:
        config.is_ollama_available = False
        logger.warning("Ollama is not available. Skipping tests that require it.")
    
    # Check if MongoDB is available
    try:
        client = MongoClient(TEST_CONNECTION_STRING, serverSelectionTimeoutMS=2000)
        client.server_info()  # Will raise if MongoDB is not available
        config.is_mongodb_available = True
        logger.warning("MongoDB is available.")
        client.close()
    except Exception as e:
        config.is_mongodb_available = False
        logger.warning(f"MongoDB is not available: {e}.  Skipping tests that require it.")

    # Check if OpenAI is available (if needed in future)
    try:
        openai_adapter = OpenAIPromptAdapter("gpt-4.1-nano", temperature=0.0)
        if openai_adapter.is_available():
            config.is_openai_available = True
            logger.warning("OpenAI is available.")
        else:
            config.is_openai_available = False
            logger.warning("OpenAI is not available. Skipping tests that require it.")
    except Exception as e:
        config.is_openai_available = False
        logger.warning(f"OpenAI check failed: {e}. Skipping tests that require it.")

@pytest.fixture
def requires_mongodb(request):
    """
    Fixture that skips tests if MongoDB is not available.
    
    Usage:
        def test_something(requires_mongodb):
            # This test will be skipped if MongoDB is not available
            ...
    """
    if not request.config.is_mongodb_available:
        pytest.skip("Test requires MongoDB, but MongoDB is not available")
    return True


@pytest.fixture
def requires_ollama(request):
    """
    Fixture that skips tests if Ollama is not available.
    
    Usage:
        def test_something(requires_ollama):
            # This test will be skipped if Ollama is not available
            ...
    """
    if not request.config.is_ollama_available:
        pytest.skip("Test requires Ollama with llama3.2, but this model or the server is not available")
    return True

@pytest.fixture
def requires_openai(request):
    """
    Fixture that skips tests if OpenAI is not available.
    
    Usage:
        def test_something(requires_openai):
            # This test will be skipped if OpenAI is not available
            ...
    """
    if not request.config.is_openai_available:
        pytest.skip("Test requires OpenAI, but OpenAI is not available")
    return True

@pytest.fixture(scope="class")
def requires_mongodb_class(request):
    """
    Class-level fixture that skips all tests in a class if MongoDB is not available.
    
    Usage:
        @pytest.mark.usefixtures("requires_mongodb_class")
        class TestSomething:
            def test_one(self):
                # This test will be skipped if MongoDB is not available
                ...
    """
    if not request.config.is_mongodb_available:
        pytest.skip("Test class requires MongoDB, but MongoDB is not available")
    return True

@pytest.fixture(scope="function")
def mongodb_client():
    """Create a real MongoDB client for integration tests.
    
    This fixture should be used when you want to test against a real MongoDB instance.
    """
    try:
        from pymongo import MongoClient
        client = MongoClient(TEST_CONNECTION_STRING, serverSelectionTimeoutMS=2000)
        # Test connection - will raise if MongoDB is not available
        client.server_info()
        
        # Drop test database if it exists (clean start)
        client.drop_database(TEST_DB_NAME)
        
        yield client
        
        # Teardown - drop test database and close connection
        client.drop_database(TEST_DB_NAME)
        client.close()
    except Exception as e:
        pytest.skip(f"Skipping test with real MongoDB: {e}")



@pytest.fixture(scope="function")
def mock_mongodb_client():
    """Create a mock MongoDB client using mongomock.
    
    This fixture should be used for pure unit tests that don't require a real MongoDB.
    """
    client = mongomock.MongoClient()
    yield client


@pytest.fixture
def patch_mongo_client(monkeypatch):
    """Patch MongoClient to use mongomock for all tests in a module.
    
    Use this fixture at the module level to make all tests use mongomock instead
    of real MongoDB connections, no matter how they're created.
    """
    def mock_mongo_client(*args, **kwargs):
        return mongomock.MongoClient()
    
    monkeypatch.setattr("pymongo.MongoClient", mock_mongo_client)
    return mock_mongo_client


@pytest.fixture
def config_with_mongo_connection(monkeypatch):
    """Set up configuration with MongoDB connection string.
    
    This fixture mocks the configuration to include the MongoDB connection string.
    """
    def mock_get_config():
        return {
            "mongo_connection_string": TEST_CONNECTION_STRING
        }
    
    monkeypatch.setattr("talkpipe.util.config.get_config", mock_get_config)
    return mock_get_config