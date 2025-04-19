"""Integration tests for the MongoInsert segment with TalkPipe pipeline.

These tests verify that the MongoInsert segment works correctly in a full TalkPipe pipeline.
"""

import pytest

import os
from pymongo import MongoClient
import tempfile
import json

from talkpipe.chatterlang import compiler
from talkpipe.pipe import io
from talkpipe.pipe.basic import ToDict
from talkpipe.data.mongo import MongoInsert, MongoSearch
from talkpipe.util.config import get_config

# Constants for testing
TEST_DB_NAME = "talkpipe_integration_test"
TEST_COLLECTION = "integration_collection"
TEST_CONNECTION_STRING = get_config().get("mongo_connection_string", None)

@pytest.mark.usefixtures("requires_mongodb_class")
class TestMongoInsertIntegration:
    """Integration tests for MongoInsert in TalkPipe pipelines."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test database and tear it down after tests."""
        # Connect to MongoDB
        self.client = MongoClient(TEST_CONNECTION_STRING)
        
        # Drop test database if it exists (clean start)
        self.client.drop_database(TEST_DB_NAME)
        
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        
        yield  # Run the test
        
        # Teardown - drop test database and remove temp directory
        self.client.drop_database(TEST_DB_NAME)
        self.client.close()
        self.temp_dir.cleanup()

    def create_test_jsonl(self, data):
        """Create a JSONL file with test data."""
        file_path = os.path.join(self.temp_dir.name, "test_data.jsonl")
        with open(file_path, "w") as f:
            for item in data:
                f.write(json.dumps(item) + "\n")
        return file_path

    def test_pipeline_with_python_api(self):
        """Test MongoInsert in a pipeline created with Python API."""
        # Create test data file
        test_data = [
            {"id": 1, "name": "User 1", "tags": ["python", "mongodb"]},
            {"id": 2, "name": "User 2", "tags": ["pipeline", "testing"]}
        ]
        test_file = self.create_test_jsonl(test_data)
        
        # Create pipeline with MongoInsert
        pipeline = (
            io.readJsonl() | 
            MongoInsert(
                connection_string=TEST_CONNECTION_STRING,
                database=TEST_DB_NAME,
                collection=TEST_COLLECTION,
                append_as="mongo_id"
            )
        )
        
        # Run pipeline
        results = list(pipeline([test_file]))
        
        # Verify results
        assert len(results) == 2
        assert all("mongo_id" in result for result in results)
        
        # Verify MongoDB data
        db = self.client[TEST_DB_NAME]
        collection = db[TEST_COLLECTION]
        docs = list(collection.find())
        assert len(docs) == 2
        
        # Verify document content
        assert docs[0]["id"] == 1
        assert docs[1]["id"] == 2

    def test_pipeline_with_field_extraction(self):
        """Test MongoInsert with field extraction in a pipeline."""
        # Create test data
        test_data = [
            {"id": 1, "user": {"name": "User 1", "email": "user1@example.com"}},
            {"id": 2, "user": {"name": "User 2", "email": "user2@example.com"}}
        ]
        test_file = self.create_test_jsonl(test_data)
        
        # Create pipeline with field extraction
        pipeline = (
            io.readJsonl() | 
            MongoInsert(
                connection_string=TEST_CONNECTION_STRING,
                database=TEST_DB_NAME,
                collection=TEST_COLLECTION,
                field="user"
            )
        )
        
        # Run pipeline
        list(pipeline([test_file]))
        
        # Verify MongoDB data
        db = self.client[TEST_DB_NAME]
        collection = db[TEST_COLLECTION]
        docs = list(collection.find())
        assert len(docs) == 2
        
        # Verify only user data was inserted
        assert docs[0]["name"] == "User 1"
        assert docs[0]["email"] == "user1@example.com"
        assert "id" not in docs[0]

    def test_chatterlang_script(self):
        """Test MongoInsert in a ChatterLang script."""
        # Create test data
        test_data = [
            {"id": 1, "profile": {"name": "User 1", "email": "user1@example.com"}},
            {"id": 2, "profile": {"name": "User 2", "email": "user2@example.com"}}
        ]
        test_file = self.create_test_jsonl(test_data)
        
        # Create ChatterLang script
        script = f"""
        | readJsonl | mongoInsert[
            connection_string="{TEST_CONNECTION_STRING}",
            database="{TEST_DB_NAME}",
            collection="{TEST_COLLECTION}",
            fields="id:user_id,profile.name:full_name,profile.email:contact_email"
        ]
        """
        
        # Compile and run the script
        pipeline = compiler.compile(script)
        list(pipeline([test_file]))
        
        # Verify MongoDB data
        db = self.client[TEST_DB_NAME]
        collection = db[TEST_COLLECTION]
        docs = list(collection.find())
        assert len(docs) == 2
        
        # Verify document structure
        assert set(docs[0].keys()) == {"_id", "user_id", "full_name", "contact_email"}
        assert docs[0]["user_id"] == 1
        assert docs[0]["full_name"] == "User 1"
        assert docs[0]["contact_email"] == "user1@example.com"

    def test_complex_pipeline(self):
        """Test MongoInsert in a complex pipeline with transformations."""
        # Create test data
        test_data = [
            {"id": 1, "value": "low", "score": 30},
            {"id": 2, "value": "medium", "score": 60},
            {"id": 3, "value": "high", "score": 90}
        ]
        test_file = self.create_test_jsonl(test_data)
        
        # Create a pipeline with filtering and transformation
        script = f"""
        | readJsonl | 
        gt[field="score", n=50] |  # Filter scores > 50
        mongoInsert[
            connection_string="{TEST_CONNECTION_STRING}",
            database="{TEST_DB_NAME}",
            collection="{TEST_COLLECTION}"
        ]
        """
        
        # Compile and run the script
        pipeline = compiler.compile(script)
        results = list(pipeline([test_file]))
        
        # Verify results
        assert len(results) == 2  # Only items with score > 50
        
        # Verify MongoDB data
        db = self.client[TEST_DB_NAME]
        collection = db[TEST_COLLECTION]
        docs = list(collection.find())
        assert len(docs) == 2
        
        # Verify only filtered documents were inserted
        scores = [doc["score"] for doc in docs]
        assert all(score > 50 for score in scores)
        values = [doc["value"] for doc in docs]
        assert set(values) == {"medium", "high"}

    def test_multiple_collections(self):
        """Test using MongoInsert with multiple collections in the same pipeline."""
        # Create test data
        test_data = [
            {"id": 1, "name": "User 1", "type": "regular"},
            {"id": 2, "name": "User 2", "type": "premium"}
        ]
        test_file = self.create_test_jsonl(test_data)
        
        # Create a fork pipeline that sends data to different collections based on type
        pipeline = compiler.compile(f"""
        | readJsonl | fork(
            # Fork 1: Regular users
            isIn[field="type", value="regular"] | 
            mongoInsert[
                connection_string="{TEST_CONNECTION_STRING}",
                database="{TEST_DB_NAME}",
                collection="regular_users"
            ],
            
            # Fork 2: Premium users
            isIn[field="type", value="premium"] | 
            mongoInsert[
                connection_string="{TEST_CONNECTION_STRING}",
                database="{TEST_DB_NAME}",
                collection="premium_users"
            ]
        )
        """)
        
        # Run the pipeline
        list(pipeline([test_file]))
        
        # Verify data in the regular users collection
        db = self.client[TEST_DB_NAME]
        regular_collection = db["regular_users"]
        regular_docs = list(regular_collection.find())
        assert len(regular_docs) == 1
        assert regular_docs[0]["type"] == "regular"
        
        # Verify data in the premium users collection
        premium_collection = db["premium_users"]
        premium_docs = list(premium_collection.find())
        assert len(premium_docs) == 1
        assert premium_docs[0]["type"] == "premium"


@pytest.mark.usefixtures("requires_mongodb_class")
class TestMongoSearchIntegration:
    """Integration tests for MongoSearch with a real MongoDB."""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test database with data and tear it down after tests."""
        # Skip these tests if no connection string provided or MongoDB not available
        # Connect to MongoDB
        
        try:
            # Connect to MongoDB
            self.client = MongoClient(TEST_CONNECTION_STRING)
            # Test connection - will raise if MongoDB is not available
            self.client.server_info()
            
            # Setup test database and collection
            self.db_name = "test_search_db"
            self.collection_name = "test_search_collection"
            
            # Drop test database if it exists (clean start)
            self.client.drop_database(self.db_name)
            
            # Create database and collection
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            
            # Insert sample documents
            self.test_docs = [
                {"name": "John", "age": 30, "email": "john@example.com", "tags": ["developer", "python"]},
                {"name": "Jane", "age": 25, "email": "jane@example.com", "tags": ["designer", "ui"]},
                {"name": "Bob", "age": 35, "email": "bob@example.com", "tags": ["developer", "java"]},
                {"name": "Alice", "age": 28, "email": "alice@example.com", "tags": ["manager", "team-lead"]}
            ]
            
            self.collection.insert_many(self.test_docs)
            
            yield  # Run the test
            
        except Exception as e:
            pytest.skip(f"Skipping MongoDB integration test: {e}")
            return
            
        finally:
            # Teardown - drop test database
            if hasattr(self, 'client'):
                self.client.drop_database(self.db_name)
                self.client.close()
    
    def test_real_connection(self):
        """Test with real MongoDB connection."""
        connection_string = pytest.importorskip("os").environ.get("TALKPIPE_mongo_connection_string")
        
        # Create segment with real connection
        segment = MongoSearch(
            connection_string=connection_string,
            database=self.db_name,
            collection=self.collection_name,
            sort=json.dumps([("age", 1)])
        )
        
        # Query for developers
        query = json.dumps({"tags": "developer"})
        
        # Process data
        results = list(segment([query]))
        
        # Verify results
        assert len(results) == 2  # John and Bob
        # Results should be sorted by age
        assert results[0]["name"] == "John"  # Younger developer
        assert results[1]["name"] == "Bob"   # Older developer
