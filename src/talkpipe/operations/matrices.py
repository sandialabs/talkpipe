from typing import Optional
import numpy as np
import umap
from sklearn.manifold import TSNE
from talkpipe import register_segment, AbstractSegment

@register_segment("reduceUMAP")
class ReduceUMAP(AbstractSegment):
    """Use UMAP to reduce dimensionality of provided matrix.
    
    This segment reduces the dimensionality of the provided matrix using UMAP.
    
    Parameters:
        n_components: The dimension of the space to embed into. Default is 2.
        n_neighbors: Size of local neighborhood. Default is 15.
        min_dist: Minimum distance between embedded points. Default is 0.1.
        metric: Distance metric for UMAP. Default is 'euclidean'.
        random_state: Random state for reproducibility.
        **umap_kwargs: Additional keyword arguments to pass to UMAP.
    """
    def __init__(self, 
                 n_components: Optional[int] = 2, 
                 n_neighbors: int = 15,
                 min_dist: float = 0.1,
                 metric: str = 'euclidean',
                 random_state: Optional[int] = None,
                 n_epochs: int = None
                ):
        super().__init__()
        self.n_components = n_components
        self.n_neighbors = n_neighbors
        self.min_dist = min_dist
        self.metric = metric
        self.random_state = random_state
        self.n_epochs = n_epochs

    def transform(self, items):
        # Convert items to numpy array
        for item in items:
            matrix = np.array(item)

            # Apply UMAP
            reducer = umap.UMAP(
                n_components=self.n_components,
                n_neighbors=min(self.n_neighbors, matrix.shape[0]-1),
                min_dist=self.min_dist,
                metric=self.metric,
                random_state=self.random_state,
                n_epochs=self.n_epochs
            )
            reduced_matrix = reducer.fit_transform(matrix)

            yield reduced_matrix


@register_segment("reduceTSNE")
class ReduceTSNE(AbstractSegment):
    """Use t-SNE to reduce dimensionality of provided matrix.
    
    This segment reduces the dimensionality of the provided matrix using t-SNE 
    (t-Distributed Stochastic Neighbor Embedding).
    
    Parameters:
        n_components: The dimension of the space to embed into. Default is 2.
        perplexity: The perplexity is related to the number of nearest neighbors used
            in other manifold learning algorithms. Larger datasets usually require a
            larger perplexity. Default is 30.
        early_exaggeration: Controls how tight natural clusters in the original 
            space are in the embedded space. Default is 12.0.
        learning_rate: The learning rate for t-SNE. Default is 200.0.
        max_iter: Maximum number of iterations for the optimization. Default is 1000.
        metric: Distance metric for t-SNE. Default is 'euclidean'.
        random_state: Random state for reproducibility.
        **tsne_kwargs: Additional keyword arguments to pass to TSNE.
    """
    
    def __init__(self,
                n_components: Optional[int] = 2,
                perplexity: float = 30.0,
                early_exaggeration: float = 12.0,
                learning_rate: float = 200.0,
                max_iter: int = 1000,
                metric: str = 'euclidean',
                random_state: Optional[int] = None,
                **tsne_kwargs
                ):
        super().__init__()
        self.n_components = n_components
        self.perplexity = perplexity
        self.early_exaggeration = early_exaggeration
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.metric = metric
        self.random_state = random_state
        self.tsne_kwargs = tsne_kwargs
    
    def transform(self, items):
        # Process each item (potentially a batch of vectors)
        for item in items:
            # Convert items to numpy array
            matrix = np.array(item)
            
            # Apply t-SNE
            reducer = TSNE(
                n_components=self.n_components,
                perplexity=self.perplexity,
                early_exaggeration=self.early_exaggeration,
                learning_rate=self.learning_rate,
                max_iter=self.max_iter,
                metric=self.metric,
                random_state=self.random_state,
                **self.tsne_kwargs
            )
            reduced_matrix = reducer.fit_transform(matrix)
            
            yield reduced_matrix

