from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional, Union
from dataclasses import dataclass, asdict
import numpy as np

# Type aliases
VectorLike = Union[List[float], np.ndarray]


@dataclass
class VectorRecord:
    """Standard vector record structure"""
    id: str
    vector: List[float]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VectorDB(ABC):
    """
    Simple abstract base class for vector databases
    
    Defines the core interface based on SimpleVectorDB
    """
    
    def __init__(self, dimension: Optional[int] = None):
        self.dimension = dimension
    
    @abstractmethod
    def add(self, vector: VectorLike, metadata: Optional[Dict[str, Any]] = None,
            vector_id: Optional[str] = None) -> str:
        """Add a vector to the database"""
        pass
    
    @abstractmethod
    def get(self, vector_id: str) -> Optional[VectorRecord]:
        """Get a vector record by ID"""
        pass
    
    @abstractmethod
    def update(self, vector_id: str, vector: Optional[VectorLike] = None,
               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update a vector and/or its metadata"""
        pass
    
    @abstractmethod
    def search(self, query_vector: VectorLike, top_k: int = 5, **kwargs) -> List[Tuple[str, float, VectorRecord]]:
        """Search for similar vectors"""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Return the number of vectors in the database"""
        pass
    
    @abstractmethod
    def list_ids(self) -> List[str]:
        """Return a list of all vector IDs"""
        pass
    
    # Convenience methods
    def __len__(self) -> int:
        return self.count()
    
    def __contains__(self, vector_id: str) -> bool:
        return self.get(vector_id) is not None