"""Unit tests for the MongoInsert segment.

These tests verify the functionality of the MongoInsert segment by creating
and deleting temporary test databases and collections.
"""

import pytest

import unittest.mock
import os
import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId

from talkpipe.data.mongo import MongoInsert  
from talkpipe.util.config import get_config

# Constants for testing
TEST_DB_NAME = "talkpipe_test_db"
TEST_COLLECTION = "test_collection"
TEST_CONNECTION_STRING = get_config().get("mongo_connection_string", None)


@pytest.mark.usefixtures("requires_mongodb_class")
class TestMongoInsert:
    """Tests for the MongoInsert segment."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test database and tear it down after tests."""
        # Connect to MongoDB
        self.client = MongoClient(TEST_CONNECTION_STRING)
        
        # Drop test database if it exists (clean start)
        self.client.drop_database(TEST_DB_NAME)
        
        # Setup test database and collection
        self.db = self.client[TEST_DB_NAME]
        self.collection = self.db[TEST_COLLECTION]
        
        yield  # Run the test
        
        # Teardown - drop test database
        self.client.drop_database(TEST_DB_NAME)
        self.client.close()

    def test_basic_insert(self):
        """Test basic document insertion."""
        # Create the segment
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION
        )
        
        # Test data
        test_data = [
            {"name": "Test User 1", "age": 30},
            {"name": "Test User 2", "age": 25}
        ]
        
        # Process data through the segment
        results = list(segment(test_data))
        
        # Verify the segment passed through all items
        assert len(results) == 2
        
        # Verify the data was inserted into MongoDB
        documents = list(self.collection.find())
        assert len(documents) == 2
        
        # Verify the content of inserted documents
        names = sorted([doc["name"] for doc in documents])
        assert names == ["Test User 1", "Test User 2"]

    def test_field_extraction(self):
        """Test extracting a specific field for insertion."""
        # Create the segment
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            field="data"
        )
        
        # Test data with nested field
        test_data = [
            {"id": 1, "data": {"name": "Test User 1", "active": True}},
            {"id": 2, "data": {"name": "Test User 2", "active": False}}
        ]
        
        # Process data through the segment
        list(segment(test_data))
        
        # Verify the data was inserted into MongoDB
        documents = list(self.collection.find())
        assert len(documents) == 2
        
        # Verify we inserted only the 'data' field content
        assert all("id" not in doc for doc in documents)
        assert all("name" in doc for doc in documents)
        
        # Check specific values
        active_values = sorted([doc["active"] for doc in documents])
        assert active_values == [False, True]

    def test_fields_parameter(self):
        """Test creating documents from multiple fields."""
        # Create the segment with fields parameter
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            fields="id:user_id,profile.name:full_name,profile.email:contact"
        )
        
        # Test data with nested fields
        test_data = [
            {
                "id": 101,
                "profile": {
                    "name": "John Doe",
                    "email": "john@example.com",
                    "phone": "555-1234"  # This shouldn't be included
                },
                "meta": {"last_login": "2023-01-01"}  # This shouldn't be included
            }
        ]
        
        # Process data through the segment
        list(segment(test_data))
        
        # Verify the document was inserted
        documents = list(self.collection.find())
        assert len(documents) == 1
        
        # Verify the document has only the specified fields with their new names
        doc = documents[0]
        assert set(doc.keys()) == {"_id", "user_id", "full_name", "contact"}
        assert doc["user_id"] == 101
        assert doc["full_name"] == "John Doe"
        assert doc["contact"] == "john@example.com"
        
        # Verify fields not specified were not included
        assert "phone" not in doc
        assert "meta" not in doc

    def test_append_mongo_id(self):
        """Test appending MongoDB ID to the original item."""
        # Create the segment with append_as
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            append_as="mongo_id"
        )
        
        # Test data
        test_data = [{"name": "Test User"}]
        
        # Process data through the segment
        results = list(segment(test_data))
        
        # Verify the MongoDB ID was appended
        assert len(results) == 1
        assert "mongo_id" in results[0]
        
        # Verify the ID is valid and matches what's in the database
        mongo_id = results[0]["mongo_id"]
        assert mongo_id is not None
        
        # Query by this ID
        doc = self.collection.find_one({"_id": ObjectId(mongo_id)})
        assert doc is not None
        assert doc["name"] == "Test User"

    def test_index_creation(self):
        """Test index creation functionality."""
        # Create the segment with index
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            create_index="email",
            unique_index=True
        )
        
        # Test data
        test_data = [{"name": "Test User", "email": "test@example.com"}]
        
        # Process data
        list(segment(test_data))
        
        # Verify index was created
        indexes = list(self.collection.list_indexes())
        
        # Find our specific index
        email_indexes = [idx for idx in indexes if "email" in idx["key"]]
        assert len(email_indexes) == 1
        
        # Verify it's unique
        email_index = email_indexes[0]
        assert email_index["unique"] is True

    def test_unique_constraint(self):
        """Test unique index constraint enforcement."""
        # Create the segment with unique index
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            create_index="email",
            unique_index=True
        )
        
        # Test data with duplicate email
        test_data = [
            {"name": "User 1", "email": "same@example.com"},
            {"name": "User 2", "email": "same@example.com"}  # Same email, should cause duplicate key error
        ]
        
        # Process data - second item should be skipped due to error
        results = list(segment(test_data))
        
        # Both items should still be returned in the results
        assert len(results) == 2
        
        # But only one document should be in the database
        docs = list(self.collection.find())
        assert len(docs) == 1
        assert docs[0]["name"] == "User 1"

    def test_non_dict_values(self):
        """Test handling of non-dictionary values."""
        # Create the segment
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION
        )
        
        # Test with various non-dict types
        test_data = [
            "Just a string",
            123,
            ["a", "list", "of", "items"]
        ]
        
        # Process data
        results = list(segment(test_data))
        
        # Verify items were processed
        assert len(results) == 3
        
        # Verify documents were created with _value field
        docs = list(self.collection.find())
        assert len(docs) == 3
        
        # Check conversion to documents with _value field
        values = sorted([doc["_value"] for doc in docs], key=lambda x: str(x))
        assert values == [123, "Just a string", ["a", "list", "of", "items"]]

    def test_none_values(self):
        """Test handling of None values."""
        # Create the segment
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            field="data"
        )
        
        # Test with None value
        test_data = [{"id": 1, "data": None}]
        
        # Process data
        results = list(segment(test_data))
        
        # Verify item was returned
        assert len(results) == 1
        
        # Verify nothing was inserted due to None value
        docs = list(self.collection.find())
        assert len(docs) == 0

    def test_empty_document(self):
        """Test handling of empty documents."""
        # Create the segment with fields that don't exist
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION,
            fields="nonexistent1,nonexistent2"
        )
        
        # Test data without the specified fields
        test_data = [{"real_field": "value"}]
        
        # Process data
        results = list(segment(test_data))
        
        # Verify item was processed
        assert len(results) == 1
        
        # Verify no documents were inserted (empty document was skipped)
        docs = list(self.collection.find())
        assert len(docs) == 0

    def test_connection_from_config(self, monkeypatch):
        """Test getting connection string from config."""
        
        # First reset the config cache to ensure clean state
        from talkpipe.util.config import reset_config
        reset_config()
        
        # Then explicitly monkeypatch get_config to return our test connection string
        def mock_get_config(*args, **kwargs):
            return {"mongo_connection_string": TEST_CONNECTION_STRING}
        
        monkeypatch.setattr("talkpipe.util.config.get_config", mock_get_config)
        
        # Create segment without explicit connection string
        segment = MongoInsert(
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION
        )
        
        # Verify the connection was established from config
        test_data = [{"name": "Config Test"}]
        list(segment(test_data))
        
        # Check if document was inserted
        docs = list(self.collection.find())
        assert len(docs) == 1
        assert docs[0]["name"] == "Config Test"

    def test_invalid_parameters(self):
        """Test validation of parameters."""
        # Test missing database
        with pytest.raises(ValueError, match="Database name is required"):
            MongoInsert(
                connection_string=TEST_CONNECTION_STRING,
                collection=TEST_COLLECTION
            )
        
        # Test missing collection
        with pytest.raises(ValueError, match="Collection name is required"):
            MongoInsert(
                connection_string=TEST_CONNECTION_STRING,
                database=TEST_DB_NAME
            )
        
        # Test conflicting field and fields parameters
        with pytest.raises(ValueError, match="Cannot specify both 'field' and 'fields'"):
            MongoInsert(
                connection_string=TEST_CONNECTION_STRING,
                database=TEST_DB_NAME,
                collection=TEST_COLLECTION,
                field="specific_field",
                fields="field1,field2"
            )

    def test_object_with_dict_attr(self):
        """Test handling of objects with __dict__ attribute."""
        # Create a class with __dict__
        class TestObject:
            def __init__(self):
                self.name = "Object Name"
                self.value = 42
        
        # Create the segment
        segment = MongoInsert(
            connection_string=TEST_CONNECTION_STRING,
            database=TEST_DB_NAME,
            collection=TEST_COLLECTION
        )
        
        # Test data with an object
        test_data = [TestObject()]
        
        # Process data
        list(segment(test_data))
        
        # Verify document was inserted with object attributes
        docs = list(self.collection.find())
        assert len(docs) == 1
        assert docs[0]["name"] == "Object Name"
        assert docs[0]["value"] == 42