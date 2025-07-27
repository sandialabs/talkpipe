import logging
import json
import pickle
from typing import List, Dict, Any, Tuple, Optional, Union, Protocol
from dataclasses import dataclass, asdict
import uuid
import numpy as np
from sklearn.cluster import KMeans
import warnings
import heapq
from talkpipe.pipe.core import segment
from talkpipe.pipe import field_segment
from talkpipe.chatterlang import register_segment
from .abstract import VectorLike, DocumentStore, VectorAddable, VectorSearchable, SearchResult, Document, DocID
from talkpipe.util.data_manipulation import extract_property, toDict
from os.path import exists
from .abstract import DocumentStore, VectorAddable, VectorSearchable

logger = logging.getLogger(__name__)


@dataclass
class VectorEntry:
    """Internal data structure for storing vector data"""
    doc_id: str
    vector: List[float]
    document: Document


class SimpleVectorDB(DocumentStore, VectorAddable, VectorSearchable):
    """A simple in-memory vector database with similarity search capabilities"""
    
    def __init__(self, dimension: Optional[int] = None):
        """
        Initialize the vector database
        
        Args:
            dimension: Expected dimension of vectors (optional, inferred from first vector)
        """
        self.dimension = dimension
        self.vectors: Dict[str, VectorEntry] = {}
        
        # K-means clustering attributes
        self.clusters_valid = False
        self.kmeans_model = None
        self.cluster_centers = None
        self.cluster_assignments = None
        self.clusters = None
        self.n_clusters = 8

    def _validate_vector(self, vector: VectorLike) -> np.ndarray:
        """Validate vector and return as numpy array"""
        vec_array = np.array(vector, dtype=np.float32)
        if vec_array.ndim != 1:
            raise ValueError("Vector must be 1-dimensional")
        if not np.issubdtype(vec_array.dtype, np.number):
            raise ValueError("Vector must contain only numbers")
        if self.dimension is None:
            self.dimension = len(vec_array)
        elif len(vec_array) != self.dimension:
            raise ValueError(f"Vector dimension {len(vec_array)} doesn't match expected {self.dimension}")
        return vec_array

    def _get_vector_matrix(self) -> Tuple[np.ndarray, List[str]]:
        """Get vector matrix and corresponding IDs"""
        if not self.vectors:
            return np.array([]), []
        
        vector_ids = list(self.vectors.keys())
        vector_matrix = np.array([self.vectors[vid].vector for vid in vector_ids], dtype=np.float32)
        return vector_matrix, vector_ids

    def _cosine_similarity_batch(self, query_vector: np.ndarray, vector_matrix: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between query and all vectors"""
        if len(vector_matrix) == 0:
            return np.array([])
        
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return np.zeros(len(vector_matrix))
        
        vector_norms = np.linalg.norm(vector_matrix, axis=1)
        valid_norms = vector_norms > 0
        
        similarities = np.zeros(len(vector_matrix))
        if np.any(valid_norms):
            dot_products = np.dot(vector_matrix[valid_norms], query_vector)
            similarities[valid_norms] = dot_products / (vector_norms[valid_norms] * query_norm)
        
        return similarities

    def _euclidean_distance_batch(self, query_vector: np.ndarray, vector_matrix: np.ndarray) -> np.ndarray:
        """Compute Euclidean distance between query and all vectors"""
        if len(vector_matrix) == 0:
            return np.array([])
        return np.linalg.norm(vector_matrix - query_vector, axis=1)

    # DocumentStore protocol implementation
    def get_document(self, doc_id: DocID) -> Optional[Document]:
        """Retrieve a document by ID."""
        entry = self.vectors.get(doc_id)
        return entry.document if entry else None

    # VectorAddable protocol implementation
    def add_vector(self, vector: VectorLike, document: Document, doc_id: Optional[DocID] = None) -> DocID:
        """Add a vector to the store."""
        vec_array = self._validate_vector(vector)
        
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        if doc_id in self.vectors:
            raise ValueError(f"Vector with ID {doc_id} already exists")
        
        self.vectors[doc_id] = VectorEntry(
            doc_id=doc_id,
            vector=vec_array.tolist(),
            document=document
        )
        
        self.clusters_valid = False
        return doc_id

    # VectorSearchable protocol implementation
    def vector_search(self, vector: VectorLike, limit: int = 10, metric: str = "cosine", method: str = "brute-force") -> List[SearchResult]:
        """Search for vectors similar to the given vector"""
        results = self.search(vector, top_k=limit, metric=metric, method=method)

        return [SearchResult(
            score=float(score),
            doc_id=vector_id,
            document=entry.document
        ) for vector_id, score, entry in results]

    def run_kmeans_clustering(self, n_clusters: Optional[int] = None, random_state: int = 42) -> None:
        """Run k-means clustering on all vectors in the database"""
        if not self.vectors:
            raise ValueError("Cannot run clustering on empty database")
        
        if n_clusters is not None:
            self.n_clusters = n_clusters
        
        vector_matrix, vector_ids = self._get_vector_matrix()
        actual_n_clusters = min(self.n_clusters, len(self.vectors))
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.kmeans_model = KMeans(n_clusters=actual_n_clusters, random_state=random_state, n_init=10)
            cluster_labels = self.kmeans_model.fit_predict(vector_matrix)
        
        self.cluster_centers = self.kmeans_model.cluster_centers_
        self.cluster_assignments = {vector_ids[i]: cluster_labels[i] for i in range(len(vector_ids))}
        
        self.clusters = {}
        for vector_id, cluster_id in self.cluster_assignments.items():
            self.clusters.setdefault(cluster_id, []).append(vector_id)
        
        self.clusters_valid = True
        print(f"K-means clustering completed with {actual_n_clusters} clusters")

    def _kmeans_search(self, query_vector: np.ndarray, top_k: int, metric: str, search_clusters: int = 3) -> List[Tuple[str, float, VectorEntry]]:
        """Search using k-means clustering"""
        if not self.clusters_valid:
            self.run_kmeans_clustering()
        
        # Find closest clusters
        if metric == "cosine":
            similarities = self._cosine_similarity_batch(query_vector, self.cluster_centers)
            closest_clusters = np.argsort(similarities)[-search_clusters:][::-1]
        else:  # euclidean
            distances = self._euclidean_distance_batch(query_vector, self.cluster_centers)
            closest_clusters = np.argsort(distances)[:search_clusters]
        
        # Search within closest clusters
        candidates = []
        for cluster_id in closest_clusters:
            if cluster_id in self.clusters:
                for vector_id in self.clusters[cluster_id]:
                    if vector_id in self.vectors:
                        entry = self.vectors[vector_id]
                        vec = np.array(entry.vector, dtype=np.float32)
                        
                        if metric == "cosine":
                            score = self._cosine_similarity_batch(query_vector, vec.reshape(1, -1))[0]
                        else:  # euclidean
                            score = -self._euclidean_distance_batch(query_vector, vec.reshape(1, -1))[0]
                        
                        candidates.append((vector_id, score, entry))
        
        return heapq.nlargest(top_k, candidates, key=lambda x: x[1])

    def search(self, query_vector: VectorLike, top_k: int = 5, metric: str = "cosine", method: str = "brute-force") -> List[Tuple[str, float, VectorEntry]]:
        """Search for similar vectors"""
        query_vec = self._validate_vector(query_vector)
        
        if not self.vectors:
            return []
        
        if method == "k-means":
            return self._kmeans_search(query_vec, top_k, metric)
        elif method in ["brute-force", "brute-force-heap"]:
            return self._brute_force_search(query_vec, top_k, metric, use_heap=(method == "brute-force-heap"))
        else:
            raise ValueError(f"Unknown search method: {method}")

    def _brute_force_search(self, query_vector: np.ndarray, top_k: int, metric: str, use_heap: bool = False) -> List[Tuple[str, float, VectorEntry]]:
        """Brute-force search implementation"""
        vector_matrix, vector_ids = self._get_vector_matrix()
        
        if metric == "cosine":
            scores = self._cosine_similarity_batch(query_vector, vector_matrix)
        elif metric == "euclidean":
            scores = -self._euclidean_distance_batch(query_vector, vector_matrix)
        else:
            raise ValueError(f"Unknown metric: {metric}")
        
        if use_heap and top_k < len(scores) // 4:
            # Use heap for small k
            heap = []
            for i, score in enumerate(scores):
                vector_id = vector_ids[i]
                entry = self.vectors[vector_id]
                
                if len(heap) < top_k:
                    heapq.heappush(heap, (score, vector_id, entry))
                elif score > heap[0][0]:
                    heapq.heapreplace(heap, (score, vector_id, entry))
            
            results = []
            while heap:
                score, vector_id, entry = heapq.heappop(heap)
                results.append((vector_id, score, entry))
            return results[::-1]
        else:
            # Use sorting
            top_indices = np.argsort(scores)[-top_k:][::-1]
            return [(vector_ids[i], scores[i], self.vectors[vector_ids[i]]) for i in top_indices]

    # Legacy methods
    def add(self, vector: VectorLike, metadata: Optional[Dict[str, Any]] = None, vector_id: Optional[str] = None) -> str:
        """Add a vector to the database (legacy method)"""
        document = {str(k): str(v) for k, v in (metadata or {}).items()}
        return self.add_vector(vector, document, vector_id)

    def get(self, vector_id: str) -> Optional[VectorEntry]:
        """Get a vector entry by ID (legacy method)"""
        return self.vectors.get(vector_id)

    def delete(self, vector_id: str) -> bool:
        """Delete a vector by ID"""
        if vector_id in self.vectors:
            del self.vectors[vector_id]
            self.clusters_valid = False
            return True
        return False

    def update(self, vector_id: str, vector: Optional[VectorLike] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a vector and/or its metadata"""
        if vector_id not in self.vectors:
            return False
        
        entry = self.vectors[vector_id]
        
        if vector is not None:
            vec_array = self._validate_vector(vector)
            entry.vector = vec_array.tolist()
            self.clusters_valid = False
        
        if metadata is not None:
            entry.document = {str(k): str(v) for k, v in metadata.items()}
        
        return True

    def filter_search(self, query_vector: VectorLike, document_filter: Dict[str, str], top_k: int = 5, metric: str = "cosine", method: str = "brute-force") -> List[Tuple[str, float, VectorEntry]]:
        """Search with document filtering"""
        # Filter vectors
        filtered_vectors = {
            vid: entry for vid, entry in self.vectors.items()
            if all(entry.document.get(k) == v for k, v in document_filter.items())
        }
        
        # Temporarily replace vectors
        original_vectors = self.vectors
        self.vectors = filtered_vectors
        
        try:
            return self.search(query_vector, top_k, metric, method)
        finally:
            self.vectors = original_vectors

    def count(self) -> int:
        """Return the number of vectors in the database"""
        return len(self.vectors)

    def list_ids(self) -> List[str]:
        """Return a list of all vector IDs"""
        return list(self.vectors.keys())

    def save(self, filepath: str) -> None:
        """Save the database to a file using pickle"""
        data = {
            'dimension': self.dimension,
            'vectors': self.vectors,
            'clusters_valid': self.clusters_valid,
            'kmeans_model': self.kmeans_model,
            'cluster_centers': self.cluster_centers,
            'cluster_assignments': self.cluster_assignments,
            'clusters': self.clusters,
            'n_clusters': self.n_clusters
        }
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    def load(self, filepath: str) -> None:
        """Load the database from a file"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.dimension = data['dimension']
            self.vectors = data['vectors']
            self.clusters_valid = data.get('clusters_valid', False)
            self.kmeans_model = data.get('kmeans_model', None)
            self.cluster_centers = data.get('cluster_centers', None)
            self.cluster_assignments = data.get('cluster_assignments', None)
            self.clusters = data.get('clusters', None)
            self.n_clusters = data.get('n_clusters', 8)

    def export_json(self, filepath: str) -> None:
        """Export database to JSON format"""
        data = {
            'dimension': self.dimension,
            'vectors': {vid: {
                'doc_id': entry.doc_id,
                'vector': entry.vector,
                'document': entry.document
            } for vid, entry in self.vectors.items()}
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def import_json(self, filepath: str) -> None:
        """Import database from JSON format"""
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.dimension = data['dimension']
            self.vectors = {vid: VectorEntry(**entry_dict) for vid, entry_dict in data['vectors'].items()}


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
        db = SimpleVectorDB()
        db.load(path)
    else:
        db = SimpleVectorDB()

    for item in items:
        vector = extract_property(item, vector_field, fail_on_missing=True)
        if not isinstance(vector, (list, tuple, np.ndarray)):
            raise ValueError(f"Vector field '{vector_field}' must be a list, tuple, or numpy array")
        metadata = toDict(item, metadata_field_list, fail_on_missing=False) if metadata_field_list else {}
        
        document = {str(k): str(v) for k, v in metadata.items()}
        db.add_vector(vector, document, vector_id)

        yield item

    if path is not None:
        db.save(path)


@register_segment("searchVector")
@segment()
def search_vector(items, path: str, vector_field = "_", top_k: int = 5, 
                  all_results_at_once: bool = False, append_as: Optional[str] = None,
                  continue_on_error: bool = True,
                  search_metric: str = "cosine", search_method: str = "brute-force"):
    """    Segment to search for similar vectors in the SimpleVectorDB.
    Args:
        vector_field: The field containing the vector data.
        top_k: Number of top results to return.
        search_metric: Similarity metric ("cosine" or "euclidean").
        search_method: Search method ("brute-force", "brute-force-heap", or "k-means").
        path: Optional path to a saved vector database.
    Yields:
        List of SearchResult objects.
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
        try:
            results = db.vector_search(query_vector, limit=top_k, metric=search_metric, method=search_method)
            if all_results_at_once:
                if append_as:
                    item[append_as] = results
                    yield item
                else:
                    yield results
            else:
                if append_as:
                    raise ValueError("append_as is not supported with all_results_at_once=False")
                else:
                    yield from results
        except Exception as e:
            logger.error(f"Error during vector search: {e}")
            if not continue_on_error:
                raise  
