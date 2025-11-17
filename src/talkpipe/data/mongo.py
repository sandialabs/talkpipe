"""MongoDB segment for inserting items into a MongoDB collection.

This segment allows you to insert items from your TalkPipe pipeline into a MongoDB collection.
"""

import logging
import json
import re
from typing import Iterable, Iterator, Optional, Union, Dict, Any, Annotated
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.config import parse_key_value_str
from talkpipe.util.data_manipulation import extract_property, assign_property
from talkpipe.util.config import get_config

logger = logging.getLogger(__name__)

@registry.register_segment("mongoInsert")
class MongoInsert(core.AbstractSegment):
    """Insert items from the input stream into a MongoDB collection.
    
    For each item received, this segment inserts it into the specified MongoDB collection
    and then yields the item back to the pipeline. This allows for both persisting data
    and continuing to process it in subsequent pipeline stages.
    """
    
    def __init__(
        self,
        connection_string: Annotated[Optional[str], "MongoDB connection string"] = None,
        database: Annotated[Optional[str], "Name of the MongoDB database to use"] = None,
        collection: Annotated[Optional[str], "Name of the MongoDB collection to use"] = None,
        field: Annotated[str, "Field to extract from each item for insertion"] = "_",
        fields: Annotated[Optional[str], "Comma-separated list of fields to extract"] = None,
        set_as: Annotated[Optional[str], "Field name to add MongoDB insertion result to item"] = None,
        create_index: Annotated[Optional[str], "Field to create an index on"] = None,
        unique_index: Annotated[bool, "Whether to create a unique index"] = False
    ):
        super().__init__()
        
        # Try to get connection string from config if not provided
        if connection_string is None:
            cfg = get_config()
            connection_string = cfg.get("mongo_connection_string")
            if not connection_string:
                raise ValueError(
                    "MongoDB connection string must be provided either directly "
                    "or via the 'mongo_connection_string' configuration setting."
                )
        
        # Validate required parameters
        if not database:
            raise ValueError("Database name is required")
        if not collection:
            raise ValueError("Collection name is required")
        
        # Validate field and fields parameters
        if field != "_" and fields is not None:
            raise ValueError("Cannot specify both 'field' and 'fields' parameters")
            
        self.connection_string = connection_string
        self.database_name = database
        self.collection_name = collection
        self.field = field
        self.fields = fields
        self.set_as = set_as
        self.create_index = create_index
        self.unique_index = unique_index
        
        # Parse fields specification if provided
        self.parsed_fields = None
        if self.fields is not None:
            self.parsed_fields = parse_key_value_str(self.fields)
        
        # Lazy-loaded client, database and collection
        self._client = None
        self._db = None
        self._collection = None
        
    def _ensure_connection(self) -> Collection:
        """Ensure MongoDB connection is established and return the collection."""
        if self._collection is None:
            logger.debug(f"Connecting to MongoDB: {self.connection_string}")
            self._client = MongoClient(self.connection_string)
            self._db = self._client[self.database_name]
            self._collection = self._db[self.collection_name]
            
            # Create index if specified
            if self.create_index:
                logger.debug(f"Creating index on {self.create_index} (unique={self.unique_index})")
                self._collection.create_index(self.create_index, unique=self.unique_index)
                
        return self._collection

    def _close_connection(self):
        """Clean up MongoDB client connection when the segment is destroyed."""
        if self._client:
            logger.debug("Closing MongoDB connection")
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None

    
    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Insert each item into the MongoDB collection.
        
        Yields:
            Each item from the input stream after inserting it into MongoDB.
            If set_as is specified, the MongoDB result is added to the item.
        """
        collection = self._ensure_connection()
        
        for item in input_iter:
            try:
                # Extract data to insert based on configuration
                if self.fields is not None:
                    # Create a new document from multiple fields
                    data_to_insert = {}
                    for source_field, target_field in self.parsed_fields.items():
                        try:
                            field_value = extract_property(item, source_field, fail_on_missing=True)
                            data_to_insert[target_field] = field_value
                        except (AttributeError, KeyError) as e:
                            logger.warning(f"Could not extract field '{source_field}': {e}")
                elif self.field == "_":
                    # Insert the entire item
                    data_to_insert = item
                else:
                    # Extract specific field
                    data_to_insert = extract_property(item, self.field)
                
                # Skip empty documents or None values
                if data_to_insert is None or (isinstance(data_to_insert, dict) and len(data_to_insert)==0):
                    logger.warning(f"Skipping empty document or None value")
                    yield item
                    continue
                
                # Ensure the document is a dictionary for MongoDB insertion
                if not isinstance(data_to_insert, dict):
                    if not hasattr(data_to_insert, '__dict__'):
                        logger.warning(
                            f"Converting non-dict value to document with '_value' field. "
                            f"Value type: {type(data_to_insert)}"
                        )
                        data_to_insert = {"_value": data_to_insert}
                    else:
                        # Convert object to dictionary if possible
                        data_to_insert = data_to_insert.__dict__
                
                # Insert into MongoDB
                logger.debug(f"Inserting into {self.database_name}.{self.collection_name}: {data_to_insert}")
                result = collection.insert_one(data_to_insert)
                
                # Add result to item if requested
                if self.set_as:
                    assign_property(item, self.set_as, str(result.inserted_id))
                
                yield item
                
            except Exception as e:
                logger.error(f"Error inserting into MongoDB: {e}")
                # Continue processing other items despite errors
                yield item
                
        self._close_connection()        

@registry.register_segment("mongoSearch")
class MongoSearch(core.AbstractSegment):
    """Search a MongoDB collection and yield results.
    
    This segment performs a query against a MongoDB collection and yields
    the matching documents one by one as they are returned from the database.
    """
    
    def __init__(
        self,
        field: Annotated[str, "Field in the incoming item to use as a query"] = "_",
        connection_string: Annotated[Optional[str], "MongoDB connection string"] = None,
        database: Annotated[Optional[str], "Name of the MongoDB database to use"] = None,
        collection: Annotated[Optional[str], "Name of the MongoDB collection to use"] = None,
        project: Annotated[Optional[str], "JSON string defining projection for returned documents"] = None,
        sort: Annotated[Optional[str], "JSON string defining sort order"] = None,
        limit: Annotated[int, "Maximum number of results to return per query"] = 0,
        skip: Annotated[int, "Number of documents to skip"] = 0,
        set_as: Annotated[Optional[str], "Field name to add MongoDB results to incoming item"] = None
    ):
        super().__init__()
        
        # Try to get connection string from config if not provided
        if connection_string is None:
            cfg = get_config()
            connection_string = cfg.get("mongo_connection_string")
            if not connection_string:
                raise ValueError(
                    "MongoDB connection string must be provided either directly "
                    "or via the 'mongo_connection_string' configuration setting."
                )
        
        # Validate required parameters
        if not database:
            raise ValueError("Database name is required")
        if not collection:
            raise ValueError("Collection name is required")
                    
        self.field=field
        self.connection_string = connection_string
        self.database_name = database
        self.collection_name = collection
        self.project = project
        self.sort = sort
        self.limit = limit
        self.skip = skip
        self.set_as = set_as
        
        # Lazy-loaded client, database and collection
        self._client = None
        self._db = None
        self._collection = None
        
    def _ensure_connection(self) -> Collection:
        """Ensure MongoDB connection is established and return the collection."""
        if self._collection is None:
            logger.debug(f"Connecting to MongoDB: {self.connection_string}")
            self._client = MongoClient(self.connection_string)
            self._db = self._client[self.database_name]
            self._collection = self._db[self.collection_name]
                
        return self._collection

    def _close_connection(self):
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None
    
    def transform(self, input_iter: Iterable[Any]) -> Iterator[Any]:
        """Search the MongoDB collection based on query parameters.
        
        Yields:
            If set_as is specified, yields each input item with results appended.
            Otherwise, yields the MongoDB results directly.
        """
        
        collection = self._ensure_connection()
        
        # Parse static queries if provided
        projection = json.loads(self.project) if self.project else None
        sort_order = json.loads(self.sort) if self.sort else None
        
        for item in input_iter:
            query_string = extract_property(item, self.field)
            actual_query = query_string
            actual_query = json.loads(query_string)
            
            logger.debug(f"Querying {self.database_name}.{self.collection_name}: {actual_query}")
            
            # Execute query with parameters
            cursor = collection.find(
                filter=actual_query,
                projection=projection,
                skip=self.skip,
                limit=self.limit,
                sort=sort_order
            )
            
            # Handle results based on configuration
            if self.set_as:
                results = list(cursor)
                assign_property(item, self.set_as, results)
                yield item
            else:
                for result in cursor:
                    yield result

        self._close_connection()
                
