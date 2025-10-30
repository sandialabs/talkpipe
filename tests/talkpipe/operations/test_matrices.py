import pytest
import numpy as np
from sklearn.datasets import make_blobs
from talkpipe.operations.matrices import ReduceTSNE


class TestReduceTSNE:
    """Test suite for the ReduceTSNE class without using mocks."""

    def test_initialization(self):
        """Test that the ReduceTSNE class initializes with default and custom parameters."""
        # Test with default parameters
        reducer = ReduceTSNE()
        assert reducer.n_components == 2
        assert reducer.perplexity == 30.0
        assert reducer.early_exaggeration == 12.0
        assert reducer.learning_rate == 200.0
        assert reducer.max_iter == 1000
        assert reducer.metric == 'euclidean'
        assert reducer.random_state is None
        assert reducer.tsne_kwargs == {}

        # Test with custom parameters
        custom_reducer = ReduceTSNE(
            n_components=3,
            perplexity=50.0,
            early_exaggeration=15.0,
            learning_rate=150.0,
            max_iter=2000,
            metric='cosine',
            random_state=42,
            method='exact'
        )
        assert custom_reducer.n_components == 3
        assert custom_reducer.perplexity == 50.0
        assert custom_reducer.early_exaggeration == 15.0
        assert custom_reducer.learning_rate == 150.0
        assert custom_reducer.max_iter == 2000
        assert custom_reducer.metric == 'cosine'
        assert custom_reducer.random_state == 42
        assert 'method' in custom_reducer.tsne_kwargs
        assert custom_reducer.tsne_kwargs['method'] == 'exact'

    def test_transform_with_random_data(self):
        """Test transformation of random data."""
        # Create random data
        np.random.seed(42)
        data = np.random.rand(50, 10)  # 50 samples, 10 features (increased from 20)

        # Create reducer with fixed random state for reproducibility
        # Using a lower perplexity to avoid the perplexity constraint
        reducer = ReduceTSNE(perplexity=15, random_state=42)  # Perplexity < 50

        # Transform the data
        result = list(reducer.transform([data]))

        # Check the result
        assert len(result) == 1
        assert result[0].shape == (50, 2)  # Default n_components is 2
        assert isinstance(result[0], np.ndarray)
        assert not np.isnan(result[0]).any()  # No NaN values

    def test_transform_with_multiple_inputs(self):
        """Test transformation of multiple input arrays."""
        # Create multiple datasets
        np.random.seed(42)
        data1 = np.random.rand(40, 8)  # 40 samples, 8 features (increased from 15)
        data2 = np.random.rand(35, 8)  # 35 samples, 8 features (increased from 10)

        # Create reducer with appropriate perplexity for both datasets
        reducer = ReduceTSNE(perplexity=10, random_state=42)  # Perplexity < 35

        # Transform the data
        result = list(reducer.transform([data1, data2]))

        # Check the results
        assert len(result) == 2
        assert result[0].shape == (40, 2)
        assert result[1].shape == (35, 2)
        assert isinstance(result[0], np.ndarray)
        assert isinstance(result[1], np.ndarray)

    def test_n_components_parameter(self):
        """Test that n_components parameter affects output dimensions."""
        # Create data
        np.random.seed(42)
        data = np.random.rand(40, 10)  # 40 samples, 10 features (increased from 20)

        # Test with 3 components and appropriate perplexity
        reducer_3d = ReduceTSNE(n_components=3, perplexity=10, random_state=42)
        result_3d = list(reducer_3d.transform([data]))
        
        # Check output shape
        assert result_3d[0].shape == (40, 3)

        # Test with 1 component
        reducer_1d = ReduceTSNE(n_components=1, perplexity=10, random_state=42)
        result_1d = list(reducer_1d.transform([data]))
        
        # Check output shape
        assert result_1d[0].shape == (40, 1)

    def test_perplexity_parameter(self):
        """Test that perplexity parameter affects the result."""
        # Create data - using enough samples to allow different perplexity values
        np.random.seed(42)
        data = np.random.rand(50, 10)  # 50 samples, 10 features

        # Create reducers with different perplexity values
        # Note: perplexity must be less than n_samples
        reducer_low = ReduceTSNE(perplexity=5, random_state=42)
        reducer_high = ReduceTSNE(perplexity=20, random_state=42)  # Lowered from 25

        # Transform the data
        result_low = list(reducer_low.transform([data]))
        result_high = list(reducer_high.transform([data]))

        # The results should be different due to different perplexity values
        # We can't predict exactly how they'll differ, but they shouldn't be identical
        assert not np.array_equal(result_low[0], result_high[0])

    def test_transform_preserves_structure(self):
        """Test that t-SNE preserves data structure by using synthetic clustered data."""
        # Create synthetic data with 3 clusters - using 90 samples to ensure perplexity constraint is met
        X, y = make_blobs(n_samples=90, centers=3, n_features=10, random_state=42)

        # Create reducer with appropriate perplexity
        reducer = ReduceTSNE(perplexity=15, random_state=42)  # Perplexity is less than n_samples/cluster

        # Transform the data
        result = list(reducer.transform([X]))
        reduced_data = result[0]

        # Check that points from the same cluster are closer together than 
        # points from different clusters
        cluster_indices = [
            np.where(y == 0)[0],
            np.where(y == 1)[0],
            np.where(y == 2)[0]
        ]
        
        # Calculate average within-cluster distances
        within_distances = []
        for indices in cluster_indices:
            cluster_points = reduced_data[indices]
            distances = []
            for i in range(len(cluster_points)):
                for j in range(i + 1, len(cluster_points)):
                    dist = np.linalg.norm(cluster_points[i] - cluster_points[j])
                    distances.append(dist)
            if distances:
                within_distances.append(np.mean(distances))
        
        avg_within_distance = np.mean(within_distances)
        
        # Calculate average between-cluster distances
        between_distances = []
        for i, indices1 in enumerate(cluster_indices):
            for j, indices2 in enumerate(cluster_indices[i+1:], i+1):
                for idx1 in indices1:
                    for idx2 in indices2:
                        dist = np.linalg.norm(reduced_data[idx1] - reduced_data[idx2])
                        between_distances.append(dist)
        
        avg_between_distance = np.mean(between_distances)
        
        # Average distance between clusters should be greater than 
        # average distance within clusters
        assert avg_between_distance > avg_within_distance

    def test_invalid_inputs(self):
        """Test error handling with invalid inputs."""
        reducer = ReduceTSNE()

        # Test with empty data
        with pytest.raises(ValueError):
            list(reducer.transform([np.array([])]))

        # Test with 1D array
        with pytest.raises((ValueError, TypeError)):
            list(reducer.transform([np.array([1, 2, 3])]))
            
        # Test with invalid perplexity (too high for the dataset)
        small_data = np.random.rand(5, 10)  # Only 5 samples
        # Create a reducer with perplexity higher than sample count
        reducer_high_perplexity = ReduceTSNE(perplexity=10)  # Greater than 5 samples
        
        # Should raise an error since perplexity must be less than n_samples
        with pytest.raises(ValueError):
            list(reducer_high_perplexity.transform([small_data]))
