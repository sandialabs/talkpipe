import logging
import json
import pickle
from typing import List, Dict, Any, Tuple, Optional, Union
from dataclasses import dataclass, asdict
import uuid
import numpy as np
from sklearn.cluster import KMeans
import warnings
import heapq
from talkpipe.pipe.core import segment
from talkpipe.pipe import field_segment
from talkpipe.chatterlang import register_segment
from talkpipe.util.data_manipulation import extract_property, toDict
from .abstract import VectorLike, VectorRecord
from os.path import exists

logger = logging.getLogger(__name__)

class SimpleVectorDB:
    """A simple in-memory vector database with similarity search capabilities"""
    
    def __init__(self, dimension: Optional[int] = None):
        """
        Initialize the vector database
        
        Args:
            dimension: Expected dimension of vectors (optional, inferred from first vector)
        """
        self.dimension = dimension
        self.vectors: Dict[str, VectorRecord] = {}
        
        # Optimization caches
        self._vector_matrix = None
        self._vector_ids_list = None
        self._norms_cache = None
        self._cache_valid = False
        
        # K-means clustering attributes
        self.clusters_valid = False
        self.kmeans_model = None
        self.cluster_centers = None
        self.cluster_assignments = None  # Maps vector_id to cluster_id
        self.clusters = None  # Maps cluster_id to list of vector_ids
        self.n_clusters = 8  # Default number of clusters

    def _validate_vector(self, vector: VectorLike) -> None:
        """Validate vector dimensions and type"""
        try:
            vec_array = np.array(vector)
        except (ValueError, TypeError):
            raise ValueError("Vector must be a list, tuple, or numpy array of numbers")
        if vec_array.ndim != 1:
            raise ValueError("Vector must be 1-dimensional")
        if not np.issubdtype(vec_array.dtype, np.number):
            raise ValueError("Vector must contain only numbers")
        if self.dimension is None:
            self.dimension = len(vec_array)
        elif len(vec_array) != self.dimension:
            raise ValueError(f"Vector dimension {len(vec_array)} doesn't match expected {self.dimension}")
    
    def _invalidate_caches(self) -> None:
        """Invalidate optimization caches"""
        self._cache_valid = False
        self._vector_matrix = None
        self._vector_ids_list = None
        self._norms_cache = None
        
    def _invalidate_clusters(self) -> None:
        """Mark clusters as invalid"""
        self.clusters_valid = False
    
    def _build_caches(self) -> None:
        """Build optimization caches for vectorized operations"""
        if self._cache_valid or not self.vectors:
            return
            
        self._vector_ids_list = list(self.vectors.keys())
        self._vector_matrix = np.array([
            self.vectors[vid].vector for vid in self._vector_ids_list
        ], dtype=np.float32)
        
        # Precompute norms for cosine similarity
        self._norms_cache = np.linalg.norm(self._vector_matrix, axis=1)
        
        self._cache_valid = True
    
    def run_kmeans_clustering(self, n_clusters: Optional[int] = None, 
                             random_state: int = 42) -> None:
        """
        Run k-means clustering on all vectors in the database
        
        Args:
            n_clusters: Number of clusters (if None, uses self.n_clusters)
            random_state: Random state for reproducibility
        """
        if not self.vectors:
            raise ValueError("Cannot run clustering on empty database")
        
        if n_clusters is not None:
            self.n_clusters = n_clusters
        
        # Ensure we don't have more clusters than vectors
        actual_n_clusters = min(self.n_clusters, len(self.vectors))
        
        # Extract vectors and IDs
        vector_ids = list(self.vectors.keys())
        vector_matrix = np.array([self.vectors[vid].vector for vid in vector_ids])
        
        # Run k-means clustering
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Suppress sklearn warnings
            self.kmeans_model = KMeans(n_clusters=actual_n_clusters, 
                                     random_state=random_state, 
                                     n_init=10)
            cluster_labels = self.kmeans_model.fit_predict(vector_matrix)
        
        # Store cluster information
        self.cluster_centers = self.kmeans_model.cluster_centers_
        self.cluster_assignments = {}
        self.clusters = {}
        
        # Organize vectors by cluster
        for i, cluster_id in enumerate(cluster_labels):
            vector_id = vector_ids[i]
            self.cluster_assignments[vector_id] = cluster_id
            
            if cluster_id not in self.clusters:
                self.clusters[cluster_id] = []
            self.clusters[cluster_id].append(vector_id)
        
        self.clusters_valid = True
        print(f"K-means clustering completed with {actual_n_clusters} clusters")
    
    def _ensure_clusters_valid(self) -> None:
        """Ensure clusters are valid, run k-means if needed"""
        if not self.clusters_valid:
            self.run_kmeans_clustering()
    
    def _cosine_similarity_vectorized(self, query_vector: np.ndarray) -> np.ndarray:
        """Vectorized cosine similarity computation"""
        self._build_caches()
        
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return np.zeros(len(self._vector_matrix))
        
        # Handle zero norms in database vectors
        valid_norms = self._norms_cache > 0
        similarities = np.zeros(len(self._vector_matrix))
        
        if np.any(valid_norms):
            dot_products = np.dot(self._vector_matrix[valid_norms], query_vector)
            similarities[valid_norms] = dot_products / (self._norms_cache[valid_norms] * query_norm)
        
        return similarities
    
    def _euclidean_distance_vectorized(self, query_vector: np.ndarray) -> np.ndarray:
        """Vectorized Euclidean distance computation"""
        self._build_caches()
        return np.linalg.norm(self._vector_matrix - query_vector, axis=1)
        
    def _cosine_similarity(self, vec1: VectorLike, vec2: VectorLike) -> float:
        """Calculate cosine similarity between two vectors using numpy"""
        # Convert to numpy arrays only once if they aren't already
        if not isinstance(vec1, np.ndarray):
            v1 = np.array(vec1, dtype=np.float32)
        else:
            v1 = vec1
        if not isinstance(vec2, np.ndarray):
            v2 = np.array(vec2, dtype=np.float32)
        else:
            v2 = vec2
        
        # Calculate norms
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        # Avoid division by zero
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return np.dot(v1, v2) / (norm1 * norm2)
    
    def _euclidean_distance(self, vec1: VectorLike, vec2: VectorLike) -> float:
        """Calculate Euclidean distance between two vectors using numpy"""
        # Convert to numpy arrays only once if they aren't already
        if not isinstance(vec1, np.ndarray):
            v1 = np.array(vec1, dtype=np.float32)
        else:
            v1 = vec1
        if not isinstance(vec2, np.ndarray):
            v2 = np.array(vec2, dtype=np.float32)
        else:
            v2 = vec2
        return np.linalg.norm(v1 - v2)
    
    def add(self, vector: VectorLike, metadata: Optional[Dict[str, Any]] = None, 
            vector_id: Optional[str] = None) -> str:
        """
        Add a vector to the database
        
        Args:
            vector: The vector to add (list, tuple, or numpy array)
            metadata: Optional metadata dictionary
            vector_id: Optional custom ID, otherwise auto-generated
            
        Returns:
            The ID of the added vector
        """
        self._validate_vector(vector)
        
        if vector_id is None:
            vector_id = str(uuid.uuid4())
        
        if vector_id in self.vectors:
            raise ValueError(f"Vector with ID {vector_id} already exists")
        
        record = VectorRecord(
            id=vector_id,
            vector=np.array(vector).tolist(),  # Store as list for JSON serialization
            metadata=metadata or {}
        )
        
        self.vectors[vector_id] = record
        
        # Invalidate caches and clusters since we added a new vector
        self._invalidate_caches()
        self._invalidate_clusters()
        
        return vector_id
    
    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """Get a vector record by ID"""
        return self.vectors.get(vector_id)
    
    def delete(self, vector_id: str) -> bool:
        """
        Delete a vector by ID
        
        Returns:
            True if vector was deleted, False if not found
        """
        if vector_id in self.vectors:
            del self.vectors[vector_id]
            # Invalidate caches and clusters since we removed a vector
            self._invalidate_caches()
            self._invalidate_clusters()
            return True
        return False
    
    def update(self, vector_id: str, vector: Optional[VectorLike] = None, 
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update a vector and/or its metadata
        
        Returns:
            True if vector was updated, False if not found
        """
        if vector_id not in self.vectors:
            return False
        
        record = self.vectors[vector_id]
        
        if vector is not None:
            self._validate_vector(vector)
            record.vector = np.array(vector).tolist()
            # Invalidate caches and clusters since we updated a vector
            self._invalidate_caches()
            self._invalidate_clusters()
        
        if metadata is not None:
            record.metadata = metadata
        
        return True
    
    def _kmeans_search(self, query_vector: VectorLike, top_k: int = 5, 
                      metric: str = "cosine", search_clusters: int = 3) -> List[Tuple[str, float, VectorRecord]]:
        """
        Search using k-means clustering
        
        Args:
            query_vector: The query vector
            top_k: Number of top results to return
            metric: Similarity metric ("cosine" or "euclidean")
            search_clusters: Number of closest clusters to search in
            
        Returns:
            List of (vector_id, similarity_score, record) tuples
        """
        self._ensure_clusters_valid()
        
        query_vec = np.array(query_vector, dtype=np.float32)
        
        # Find closest cluster centers
        cluster_distances = []
        for cluster_id, center in enumerate(self.cluster_centers):
            if metric == "cosine":
                # For cosine similarity, we want the closest (highest similarity)
                similarity = self._cosine_similarity(query_vec, center)
                cluster_distances.append((cluster_id, -similarity))  # Negative for sorting
            else:  # euclidean
                distance = self._euclidean_distance(query_vec, center)
                cluster_distances.append((cluster_id, distance))
        
        # Sort by distance and take top clusters
        cluster_distances.sort(key=lambda x: x[1])
        closest_clusters = [cluster_id for cluster_id, _ in cluster_distances[:search_clusters]]
        
        # Search within the closest clusters using heap for efficiency
        candidates = []
        for cluster_id in closest_clusters:
            if cluster_id in self.clusters:
                for vector_id in self.clusters[cluster_id]:
                    if vector_id in self.vectors:
                        record = self.vectors[vector_id]
                        if metric == "cosine":
                            score = self._cosine_similarity(query_vector, record.vector)
                        else:  # euclidean
                            distance = self._euclidean_distance(query_vector, record.vector)
                            score = -distance  # Negative for consistent sorting
                        candidates.append((vector_id, score, record))
        
        # Use heapq for efficient top-k selection
        return heapq.nlargest(top_k, candidates, key=lambda x: x[1])
    
    def search(self, query_vector: VectorLike, top_k: int = 5, 
               metric: str = "cosine", method: str = "brute-force") -> List[Tuple[str, float, VectorRecord]]:
        """
        Search for similar vectors
        
        Args:
            query_vector: The query vector (list, tuple, or numpy array)
            top_k: Number of top results to return
            metric: Similarity metric ("cosine" or "euclidean")
            method: Search method ("brute-force" [vectorized], "brute-force-heap", or "k-means")
            
        Returns:
            List of (vector_id, similarity_score, record) tuples
        """
        self._validate_vector(query_vector)
        
        if not self.vectors:
            return []
        
        if method == "k-means":
            return self._kmeans_search(query_vector, top_k, metric)
        elif method == "brute-force":
            # Default to vectorized 
            return self._brute_force_search_vectorized(query_vector, top_k, metric)
        elif method == "brute-force-heap":
            # Keep heap version for rare edge cases
            return self._brute_force_search_heap(query_vector, top_k, metric)
        else:
            raise ValueError(f"Unknown search method: {method}. Use 'brute-force', 'brute-force-heap', or 'k-means'")
    
    def _brute_force_search_vectorized(self, query_vector: VectorLike, top_k: int = 5, 
                                     metric: str = "cosine") -> List[Tuple[str, float, VectorRecord]]:
        """
        Optimized vectorized brute-force search implementation
        """
        if not self.vectors:
            return []
            
        query_vec = np.array(query_vector, dtype=np.float32)
        
        if metric == "cosine":
            scores = self._cosine_similarity_vectorized(query_vec)
        elif metric == "euclidean":
            distances = self._euclidean_distance_vectorized(query_vec)
            scores = -distances  # Negative for consistent sorting (higher is better)
        else:
            raise ValueError(f"Unknown metric: {metric}")
        
        # Use argpartition for efficient top-k selection when k << n
        if top_k < len(scores) // 4:  # Use argpartition when k is small relative to n
            top_indices = np.argpartition(scores, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]
        else:
            top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            vector_id = self._vector_ids_list[idx]
            score = scores[idx]
            record = self.vectors[vector_id]
            results.append((vector_id, score, record))
        
        return results
    
    def _brute_force_search_heap(self, query_vector: VectorLike, top_k: int = 5, 
                           metric: str = "cosine") -> List[Tuple[str, float, VectorRecord]]:
        """
        Optimized brute-force search implementation using heap
        """
        if not self.vectors:
            return []
            
        query_vec = np.array(query_vector, dtype=np.float32)
        
        # Use a min-heap to maintain top-k results efficiently
        # For heap, we negate scores since heapq is a min-heap
        heap = []
        
        for vector_id, record in self.vectors.items():
            if metric == "cosine":
                score = self._cosine_similarity(query_vec, record.vector)
            elif metric == "euclidean":
                distance = self._euclidean_distance(query_vec, record.vector)
                score = -distance  # Negative for consistent sorting
            else:
                raise ValueError(f"Unknown metric: {metric}")
            
            if len(heap) < top_k:
                heapq.heappush(heap, (score, vector_id, record))
            elif score > heap[0][0]:  # Better than worst in heap
                heapq.heapreplace(heap, (score, vector_id, record))
        
        # Convert heap to sorted list (best first)
        results = []
        while heap:
            score, vector_id, record = heapq.heappop(heap)
            results.append((vector_id, score, record))
        
        results.reverse()  # Reverse to get best scores first
        return results
    
    def filter_search(self, query_vector: VectorLike, 
                     metadata_filter: Dict[str, Any], 
                     top_k: int = 5, metric: str = "cosine", 
                     method: str = "brute-force") -> List[Tuple[str, float, VectorRecord]]:
        """
        Search with metadata filtering
        
        Args:
            query_vector: The query vector (list, tuple, or numpy array)
            metadata_filter: Dictionary of metadata key-value pairs to filter by
            top_k: Number of top results to return
            metric: Similarity metric ("cosine" or "euclidean")
            method: Search method ("brute-force" [vectorized], "brute-force-heap", or "k-means")
            
        Returns:
            List of (vector_id, similarity_score, record) tuples
        """
        # First filter by metadata
        filtered_vectors = {}
        for vector_id, record in self.vectors.items():
            match = True
            for key, value in metadata_filter.items():
                if key not in record.metadata or record.metadata[key] != value:
                    match = False
                    break
            if match:
                filtered_vectors[vector_id] = record
        
        # Temporarily replace vectors for search
        original_vectors = self.vectors
        original_cache_valid = self._cache_valid
        self.vectors = filtered_vectors
        self._invalidate_caches()  # Force cache rebuild with filtered data
        
        try:
            results = self.search(query_vector, top_k, metric, method)
        finally:
            # Restore original vectors and cache state
            self.vectors = original_vectors
            self._cache_valid = original_cache_valid
        
        return results
    
    def count(self) -> int:
        """Return the number of vectors in the database"""
        return len(self.vectors)
    
    def list_ids(self) -> List[str]:
        """Return a list of all vector IDs"""
        return list(self.vectors.keys())
    
    def save(self, filepath: str) -> None:
        """Save the database to a file using pickle"""
        with open(filepath, 'wb') as f:
            pickle.dump({
                'dimension': self.dimension,
                'vectors': self.vectors,
                'clusters_valid': self.clusters_valid,
                'kmeans_model': self.kmeans_model,
                'cluster_centers': self.cluster_centers,
                'cluster_assignments': self.cluster_assignments,
                'clusters': self.clusters,
                'n_clusters': self.n_clusters
            }, f)
    
    def load(self, filepath: str) -> None:
        """Load the database from a file"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.dimension = data['dimension']
            self.vectors = data['vectors']
            
            # Load clustering attributes if present (for backwards compatibility)
            self.clusters_valid = data.get('clusters_valid', False)
            self.kmeans_model = data.get('kmeans_model', None)
            self.cluster_centers = data.get('cluster_centers', None)
            self.cluster_assignments = data.get('cluster_assignments', None)
            self.clusters = data.get('clusters', None)
            self.n_clusters = data.get('n_clusters', 8)
            
            # Invalidate caches after loading
            self._invalidate_caches()
    
    def export_json(self, filepath: str) -> None:
        """Export database to JSON format"""
        data = {
            'dimension': self.dimension,
            'vectors': {vid: record.to_dict() for vid, record in self.vectors.items()}
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def import_json(self, filepath: str) -> None:
        """Import database from JSON format"""
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.dimension = data['dimension']
            self.vectors = {}
            for vid, record_dict in data['vectors'].items():
                self.vectors[vid] = VectorRecord(**record_dict)
            # Invalidate caches after importing
            self._invalidate_caches()

@register_segment("addVector")
@segment()
def add_vector(items: str, path, vector_field: str = "_", vector_id: Optional[str] = None, 
               metadata_field_list: Optional[str] = None, overwrite: bool = False):
    """
    Segment to add a vector to the SimpleVectorDB.
    
    Args:
        item: The item containing the vector data.
        vector_field: The field containing the vector data.
        vector_id: Optional custom ID for the vector.
        metadata_field_list: Optional metadata field list.
        dimension: Expected dimension of the vector (optional).

    Returns:
        The ID of the added vector.
    """
    
    if path is not None and exists(path) and not overwrite:
        # Load the vector database from a file
        db = SimpleVectorDB()
        db.load(path)
    else:
        # Create a new in-memory vector database
        db = SimpleVectorDB()

    for item in items:

        vector = extract_property(item, vector_field, fail_on_missing=True)
        if not isinstance(vector, (list, tuple, np.ndarray)):
            raise ValueError(f"Vector field '{vector_field}' must be a list, tuple, or numpy array")
        metadata = toDict(item, metadata_field_list, fail_on_missing=False) if metadata_field_list else {}
        db.add(vector, metadata=metadata, vector_id=vector_id)

        yield item

    if path is not None:
        # Save the vector database to a file
        db.save(path)

@register_segment("searchVector")
@segment()
def search_vector(items, path: str, vector_field = "_", top_k: int = 5, 
                  search_metric: str = "cosine", search_method: str = "brute-force"):
    """    Segment to search for similar vectors in the SimpleVectorDB.
    Args:
        vector_field: The field containing the vector data.
        top_k: Number of top results to return.
        search_metric: Similarity metric ("cosine" or "euclidean").
        search_method: Search method ("brute-force", "brute-force-heap", or "k-means").
        path: Optional path to a saved vector database.
    Yields:
        List of tuples containing (vector_id, similarity_score, VectorRecord).
    """
    if path is None:
        logger.warning("No path provided, using in-memory vector database")

    db = SimpleVectorDB()
    if path is not None and exists(path):
        db.load(path)
        
    for item in items:
        query_vector = extract_property(item, vector_field, fail_on_missing=True)
        if not isinstance(query_vector, (list, tuple, np.ndarray)):
            raise ValueError(f"Query vector must be a list, tuple, or numpy array")
        results = db.search(query_vector, top_k=top_k, metric=search_metric,
                            method=search_method)
        yield results