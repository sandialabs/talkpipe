from deprecated import deprecated
from typing import Optional, Annotated
import numpy as np
import umap
from sklearn.manifold import TSNE
from talkpipe import register_segment, AbstractSegment

@register_segment("reduceUMAP")
@deprecated(reason="This segment is deprecated and will be removed in version 1.0.")
class ReduceUMAP(AbstractSegment):
    """Use UMAP to reduce dimensionality of provided matrix.
    
    This segment reduces the dimensionality of the provided matrix using UMAP.
    """
    def __init__(self, 
                 n_components: Annotated[Optional[int], "The dimension of the space to embed into"] = 2, 
                 n_neighbors: Annotated[int, "Size of local neighborhood"] = 15,
                 min_dist: Annotated[float, "Minimum distance between embedded points"] = 0.1,
                 metric: Annotated[str, "Distance metric for UMAP"] = 'euclidean',
                 random_state: Annotated[Optional[int], "Random state for reproducibility"] = None,
                 n_epochs: Annotated[Optional[int], "Number of training epochs"] = None
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
    """
    
    def __init__(self,
                n_components: Annotated[Optional[int], "The dimension of the space to embed into"] = 2,
                perplexity: Annotated[float, "The perplexity is related to the number of nearest neighbors used in other manifold learning algorithms"] = 30.0,
                early_exaggeration: Annotated[float, "Controls how tight natural clusters in the original space are in the embedded space"] = 12.0,
                learning_rate: Annotated[float, "The learning rate for t-SNE"] = 200.0,
                max_iter: Annotated[int, "Maximum number of iterations for the optimization"] = 1000,
                metric: Annotated[str, "Distance metric for t-SNE"] = 'euclidean',
                random_state: Annotated[Optional[int], "Random state for reproducibility"] = None,
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

