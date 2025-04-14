"""PyTest configuration for MongoDB tests.

Provides fixtures for both real MongoDB testing and mocked testing.
"""

import pytest
import os
import mongomock
import unittest.mock

# Constants for testing
TEST_DB_NAME = "talkpipe_test_db"
TEST_COLLECTION = "test_collection"
TEST_CONNECTION_STRING = os.environ.get("TALKPIPE_mongo_connection_string")


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