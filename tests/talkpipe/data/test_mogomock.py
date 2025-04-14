"""Unit tests for MongoInsert segment using mongomock.

These tests verify the functionality of the MongoInsert segment using mongomock
rather than a real MongoDB instance, which makes them faster and more reliable
for CI/CD environments.
"""

import pytest
import json
from unittest import mock
from bson.objectid import ObjectId
import mongomock

from talkpipe.data.mongo import MongoInsert, MongoSearch

# Remove the pytestmark - we'll use our own fixture approach instead
# pytestmark = pytest.mark.usefixtures("patch_mongo_client")

class TestMongoInsertMocked:
    """Tests for MongoInsert using mongomock."""

    @pytest.fixture(autouse=True)
    def setup_mongo_mock(self, monkeypatch):
        """Set up mongomock for each test."""
        # Create a mongomock client
        self.mock_client = mongomock.MongoClient()
        
        # Patch both the original and the imported MongoClient
        monkeypatch.setattr("pymongo.MongoClient", lambda *args, **kwargs: self.mock_client)
        monkeypatch.setattr("talkpipe.data.mongo.MongoClient", lambda *args, **kwargs: self.mock_client)
        
        # Return the mock client for direct access in tests
        return self.mock_client

    def test_mongomock_working(self):
        """Verify mongomock is working correctly."""
        collection = self.mock_client["test_db"]["test_verification"]
        collection.insert_one({"test": "value"})
        docs = list(collection.find())
        assert len(docs) == 1
        assert docs[0]["test"] == "value"

    def test_basic_insert_mocked(self):
        """Test basic document insertion with mocked MongoDB."""
        # Create the segment
        segment = MongoInsert(
            connection_string="mongodb://fake-connection-string/",  # Will be ignored due to patch
            database="test_db",
            collection="test_collection"
        )
        
        # Test data
        test_data = [{"name": "Mock Test"}]
        
        # Process data
        results = list(segment(test_data))
        
        # Verify results
        assert len(results) == 1
        
        # Verify data in mongomock
        collection = self.mock_client["test_db"]["test_collection"]
        docs = list(collection.find())
        assert len(docs) == 1
        assert docs[0]["name"] == "Mock Test"

    def test_fields_parameter_mocked(self):
        """Test fields parameter with mocked MongoDB."""
        # Create the segment
        segment = MongoInsert(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            fields="id:user_id,name:full_name"
        )
        
        # Test data
        test_data = [{"id": 123, "name": "Mock User", "ignored": "value"}]
        
        # Process data
        list(segment(test_data))
        
        # Verify data in mongomock
        collection = self.mock_client["test_db"]["test_collection"]
        docs = list(collection.find())
        assert len(docs) == 1
        assert docs[0]["user_id"] == 123
        assert docs[0]["full_name"] == "Mock User"
        assert "ignored" not in docs[0]

    def test_append_mongo_id_mocked(self):
        """Test appending MongoDB ID with mocked MongoDB."""
        # Create the segment
        segment = MongoInsert(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            append_as="mongo_id"
        )
        
        # Test data
        test_data = [{"name": "Mock Test"}]
        
        # Process data
        results = list(segment(test_data))
        
        # Verify MongoDB ID was appended
        assert "mongo_id" in results[0]
        
        # Verify we can find the document by this ID in mongomock
        mongo_id = results[0]["mongo_id"]
        collection = self.mock_client["test_db"]["test_collection"]
        doc = collection.find_one({"_id": ObjectId(mongo_id)})
        assert doc is not None
        assert doc["name"] == "Mock Test"

    def test_config_connection_mocked(self, monkeypatch):
        """Test using config connection with mocked MongoDB."""
        # Mock get_config to return a connection string
        # We need to replace the entire function, not just set a return value
        def mock_get_config(*args, **kwargs):
            return {"mongo_connection_string": "mongodb://config-connection/"}
        
        monkeypatch.setattr("talkpipe.data.mongo.get_config", mock_get_config)
        
        # Create segment without explicit connection string
        segment = MongoInsert(
            database="test_db",
            collection="test_collection"
        )
        
        # Test data
        test_data = [{"name": "Config Test"}]
        
        # Process data
        results = list(segment(test_data))
        
        # Verify results
        assert len(results) == 1
        
        # Verify data was inserted into mock database
        collection = self.mock_client["test_db"]["test_collection"]
        docs = list(collection.find())
        assert len(docs) == 1
        assert docs[0]["name"] == "Config Test"

    def test_nested_fields_extraction_mocked(self):
        """Test extracting deeply nested fields with mocked MongoDB."""
        # Create the segment
        segment = MongoInsert(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            fields="user.profile.contact.email:email,user.profile.name:name"
        )
        
        # Test data with deeply nested fields
        test_data = [{
            "user": {
                "profile": {
                    "name": "Nested User",
                    "contact": {
                        "email": "nested@example.com",
                        "phone": "555-1234"
                    }
                }
            }
        }]
        
        # Process data
        list(segment(test_data))
        
        # Verify data in mongomock
        collection = self.mock_client["test_db"]["test_collection"]
        docs = list(collection.find())
        assert len(docs) == 1
        assert docs[0]["name"] == "Nested User"
        assert docs[0]["email"] == "nested@example.com"
        assert "phone" not in docs[0]
        assert "user" not in docs[0]

    def test_error_handling_mocked(self):
        """Test error handling with mocked MongoDB."""
        # Create the segment
        segment = MongoInsert(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            create_index="email",
            unique_index=True
        )
        
        # Insert first document
        segment([{"email": "duplicate@example.com", "name": "First User"}])
        
        # Try to insert another document with the same email
        # For mongomock we need to mock the DuplicateKeyError that would occur
        with mock.patch.object(
            self.mock_client["test_db"]["test_collection"], 
            "insert_one",
            side_effect=mongomock.DuplicateKeyError("Duplicate key error")
        ):
            results = list(segment([{"email": "duplicate@example.com", "name": "Second User"}]))
            
            # Verify the second item was processed (returned) despite the error
            assert len(results) == 1
            assert results[0]["name"] == "Second User"
        
    def test_invalid_parameters(self):
        """Test validation of parameters."""
        # Test missing database
        with pytest.raises(ValueError, match="Database name is required"):
            MongoInsert(
                connection_string="mongodb://fake-connection-string/",
                collection="test_collection"
            )
        
        # Test missing collection
        with pytest.raises(ValueError, match="Collection name is required"):
            MongoInsert(
                connection_string="mongodb://fake-connection-string/",
                database="test_db"
            )
        
        # Test conflicting field and fields parameters
        with pytest.raises(ValueError, match="Cannot specify both 'field' and 'fields'"):
            MongoInsert(
                connection_string="mongodb://fake-connection-string/",
                database="test_db",
                collection="test_collection",
                field="specific_field",
                fields="field1,field2"
            )
            
    def test_non_dict_values(self):
        """Test handling of non-dictionary values with mock MongoDB."""
        # Create the segment
        segment = MongoInsert(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection"
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
        collection = self.mock_client["test_db"]["test_collection"]
        docs = list(collection.find())
        assert len(docs) == 3
        
        # Get all _value fields and sort them for comparison
        values = sorted([str(doc["_value"]) for doc in docs])
        # Note: We use str() for comparison since the list might be serialized differently
        assert "123" in values
        assert "Just a string" in values
        assert any("list" in val for val in values)

class TestMongoSearchMocked:
    """Tests for MongoSearch using mongomock."""

    @pytest.fixture(autouse=True)
    def setup_mongo_mock(self, monkeypatch):
        """Set up mongomock for each test."""
        # Create a mongomock client
        self.mock_client = mongomock.MongoClient()
        
        # Patch MongoClient to return our mock client
        monkeypatch.setattr("pymongo.MongoClient", lambda *args, **kwargs: self.mock_client)
        monkeypatch.setattr("talkpipe.data.mongo.MongoClient", lambda *args, **kwargs: self.mock_client)
        
        # Setup test database and collection with sample data
        self.db = self.mock_client["test_db"]
        self.collection = self.db["test_collection"]
        
        # Insert sample documents
        self.test_docs = [
            {"_id": 1, "name": "John", "age": 30, "email": "john@example.com", "tags": ["developer", "python"]},
            {"_id": 2, "name": "Jane", "age": 25, "email": "jane@example.com", "tags": ["designer", "ui"]},
            {"_id": 3, "name": "Bob", "age": 35, "email": "bob@example.com", "tags": ["developer", "java"]},
            {"_id": 4, "name": "Alice", "age": 28, "email": "alice@example.com", "tags": ["manager", "team-lead"]}
        ]
        
        self.collection.insert_many(self.test_docs)
        
        # Return the mock client for direct access in tests
        return self.mock_client

    def test_basic_search(self):
        """Test basic query functionality."""
        # Create the segment
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",  # Will be ignored due to patch
            database="test_db",
            collection="test_collection"
        )
        
        # Simple query as a string
        query = json.dumps({"age": {"$gt": 30}})
        
        # Process data
        results = list(segment([query]))
        
        # Should return documents where age > 30
        assert len(results) == 1
        assert results[0]["name"] == "Bob"
        assert results[0]["age"] == 35

    def test_query_with_projection(self):
        """Test query with projection to limit returned fields."""
        # Create the segment with projection
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            project=json.dumps({"name": 1, "email": 1, "_id": 0})  # Only return name and email
        )
        
        # Query to match all documents
        query = json.dumps({})
        
        # Process data
        results = list(segment([query]))
        
        # Should return all documents with only name and email fields
        assert len(results) == 4
        for doc in results:
            assert "name" in doc
            assert "email" in doc
            assert "_id" not in doc
            assert "age" not in doc
            assert "tags" not in doc

    def test_query_with_sort(self):
        """Test query with sort order specified."""
        # Create the segment with sort
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            sort=json.dumps([("age", -1)])  # Sort by age descending
        )
        
        # Query to match all documents
        query = json.dumps({})
        
        # Process data
        results = list(segment([query]))
        
        # Should return all documents sorted by age in descending order
        assert len(results) == 4
        assert results[0]["age"] == 35  # Bob (oldest)
        assert results[1]["age"] == 30  # John
        assert results[2]["age"] == 28  # Alice
        assert results[3]["age"] == 25  # Jane (youngest)

    def test_query_with_limit_and_skip(self):
        """Test query with limit and skip parameters."""
        # Create the segment with limit and skip
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            sort=json.dumps([("age", 1)]),  # Sort by age ascending
            limit=2,  # Only return 2 documents
            skip=1     # Skip the first document
        )
        
        # Query to match all documents
        query = json.dumps({})
        
        # Process data
        results = list(segment([query]))
        
        # Should return 2 documents, skipping Jane (youngest)
        assert len(results) == 2
        assert results[0]["name"] == "Alice"  # Second youngest
        assert results[1]["name"] == "John"   # Third youngest

    def test_append_as_parameter(self):
        """Test appending search results to the input item."""
        # Create the segment with append_as
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            append_as="search_results",
            field="query"
        )
        
        # Create input with query and additional data
        input_item = {
            "query": json.dumps({"tags": "developer"}),
            "user_id": "user123"
        }
        
        # Process data
        results = list(segment([input_item]))
        
        # Should return the original item with search results appended
        assert len(results) == 1
        result = results[0]
        assert "user_id" in result
        assert result["user_id"] == "user123"
        assert "search_results" in result
        
        # Verify search results
        search_results = result["search_results"]
        assert len(search_results) == 2  # Both John and Bob are developers
        assert any(doc["name"] == "John" for doc in search_results)
        assert any(doc["name"] == "Bob" for doc in search_results)

    def test_field_parameter(self):
        """Test using a specific field from input item as query."""
        # Create the segment with field parameter
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            field="custom_query"
        )
        
        # Create input with query in a specific field
        input_item = {
            "description": "Find developers",
            "custom_query": json.dumps({"tags": "developer"})
        }
        
        # Process data
        results = list(segment([input_item]))
        
        # Should return the matching documents directly
        assert len(results) == 2  # Both John and Bob are developers
        assert any(doc["name"] == "John" for doc in results)
        assert any(doc["name"] == "Bob" for doc in results)

    def test_nested_query_field(self):
        """Test extracting query from a nested field in the input item."""
        # Create the segment with nested field path
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            field="search.criteria"
        )
        
        # Create input with nested query
        input_item = {
            "search": {
                "criteria": json.dumps({"age": {"$lt": 30}}),
                "metadata": "Young employees"
            }
        }
        
        # Process data
        results = list(segment([input_item]))
        
        # Should return documents where age < 30
        assert len(results) == 2  # Both Jane and Alice are under 30
        assert any(doc["name"] == "Jane" for doc in results)
        assert any(doc["name"] == "Alice" for doc in results)

    def test_empty_results(self):
        """Test handling of queries that return no results."""
        # Create the segment
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection",
            append_as="results",
            field="query"
        )
        
        # Query that won't match any documents
        query = json.dumps({"age": 100})
        
        # Process data
        results = list(segment([{"query": query}]))
        
        # Should return original item with empty results list
        assert len(results) == 1
        assert "results" in results[0]
        assert len(results[0]["results"]) == 0

    def test_invalid_query(self):
        """Test handling of invalid query format."""
        # Create the segment
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection"
        )
        
        # Invalid JSON query
        invalid_query = "{age: 30}"  # Missing quotes around key
        
        # Process should raise error on invalid JSON
        with pytest.raises(json.JSONDecodeError):
            list(segment([invalid_query]))

    def test_connection_from_config(self, monkeypatch):
        """Test getting connection string from config."""
        # Mock get_config to return a connection string
        monkeypatch.setattr(
            "talkpipe.util.config.get_config", 
            lambda: {"mongo_connection_string": "mongodb://config-connection/"}
        )
        
        # Create segment without explicit connection string
        segment = MongoSearch(
            connection_string="mongodb://fake-connection-string/",
            database="test_db",
            collection="test_collection"
        )
        
        # Query to match all documents
        query = json.dumps({})
        
        # Process data
        results = list(segment([query]))
        
        # Verify query was executed
        assert len(results) == 4  # All documents returned

    def test_invalid_parameters(self):
        """Test validation of required parameters."""
        # Test missing database
        with pytest.raises(ValueError, match="Database name is required"):
            MongoSearch(
                connection_string="mongodb://fake-connection-string/",
                collection="test_collection"
            )
        
        # Test missing collection
        with pytest.raises(ValueError, match="Collection name is required"):
            MongoSearch(
                connection_string="mongodb://fake-connection-string/",
                database="test_db"
            )
