import pytest
import numpy as np
from sklearn.datasets import make_blobs
from talkpipe.operations.matrices import ReduceUMAP, ReduceTSNE

class TestUMAP:
    """Tests for the UMAP dimensionality reduction segment."""

    def test_initialization(self):
        """Test that the UMAP segment initializes with correct default parameters."""
        umap_segment = ReduceUMAP()
        assert umap_segment.n_components == 2
        assert umap_segment.n_neighbors == 15
        assert umap_segment.min_dist == 0.1
        assert umap_segment.metric == 'euclidean'
        assert umap_segment.random_state is None

    def test_custom_initialization(self):
        """Test that the UMAP segment initializes with custom parameters."""
        umap_segment = ReduceUMAP(
            n_components=3,
            n_neighbors=10,
            min_dist=0.2,
            metric='cosine',
            random_state=42,
        )
        assert umap_segment.n_components == 3
        assert umap_segment.n_neighbors == 10
        assert umap_segment.min_dist == 0.2
        assert umap_segment.metric == 'cosine'
        assert umap_segment.random_state == 42

    def test_transform_single_matrix(self):
        """Test transforming a single matrix with UMAP."""
        # Create segment and random test data
        umap_segment = ReduceUMAP(n_components=2, random_state=42)  # Set random state for reproducibility
        test_matrix = np.random.rand(20, 5)  # 20 samples, 5 features
        
        # Transform
        result = list(umap_segment([test_matrix]))
        
        # Verify
        assert len(result) == 1
        assert isinstance(result[0], np.ndarray)
        assert result[0].shape == (20, 2)  # Check reduced dimensionality
        # The output values will be determined by UMAP algorithm, so we don't check specific values

    def test_transform_multiple_matrices(self):
        """Test transforming multiple matrices with UMAP."""
        # Create segment and test data
        umap_segment = ReduceUMAP(n_components=2, random_state=42)
        test_matrix1 = np.random.rand(10, 5)  # 10 samples, 5 features
        test_matrix2 = np.random.rand(15, 8)  # 15 samples, 8 features
        
        # Transform
        result = list(umap_segment([test_matrix1, test_matrix2]))
        
        # Verify
        assert len(result) == 2
        assert result[0].shape == (10, 2)  # First matrix reduced to 2D
        assert result[1].shape == (15, 2)  # Second matrix reduced to 2D

    def test_transform_with_different_components(self):
        """Test UMAP reduction with different numbers of components."""
        # Test data
        test_matrix = np.random.rand(15, 10)  # 15 samples, 10 features
        
        # Test with 3 components
        umap_segment3d = ReduceUMAP(n_components=3, random_state=42)
        result3d = list(umap_segment3d([test_matrix]))[0]
        assert result3d.shape == (15, 3)
        
        # Test with 1 component
        umap_segment1d = ReduceUMAP(n_components=1, random_state=42)
        result1d = list(umap_segment1d([test_matrix]))[0]
        assert result1d.shape == (15, 1)

    def test_transform_empty_list(self):
        """Test behavior when an empty list is provided."""
        umap_segment = ReduceUMAP()
        result = list(umap_segment([]))
        assert len(result) == 0

    def test_transform_small_dataset(self):
        """Test handling of edge cases like small matrices."""
        # Create segment
        umap_segment = ReduceUMAP(n_components=2, random_state=42, n_neighbors=3)  # Reduce n_neighbors for small dataset
        
        # Test with small matrix - note that UMAP typically needs more samples than n_neighbors
        test_matrix = np.random.rand(5, 4)  # 5 samples, 4 features
        
        # Transform
        result = list(umap_segment([test_matrix]))
        
        # Verify
        assert len(result) == 1
        assert result[0].shape == (5, 2)

    def test_transform_with_list_input(self):
        """Test that list inputs are properly converted to numpy arrays."""
        # Create segment
        umap_segment = ReduceUMAP(random_state=42)
        
        # Python list input
        test_list = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], 
                     [10.0, 11.0, 12.0], [13.0, 14.0, 15.0]]  # 5 samples, 3 features
        
        # Transform
        result = list(umap_segment([test_list]))
        
        # Verify
        assert len(result) == 1
        assert isinstance(result[0], np.ndarray)
        assert result[0].shape == (5, 2)

    def test_custom_parameters_affect_output(self):
        """Test that different parameters produce different UMAP embeddings."""
        # Create test data
        test_matrix = np.random.rand(30, 8)  # 30 samples, 8 features
        
        # Create segments with different parameters
        umap_default = ReduceUMAP(random_state=42)
        umap_custom = ReduceUMAP(
            n_neighbors=5,  # Smaller neighborhood
            min_dist=0.5,   # Larger minimum distance
            random_state=42  # Same seed for comparability
        )
        
        # Transform
        result_default = list(umap_default([test_matrix]))[0]
        result_custom = list(umap_custom([test_matrix]))[0]
        
        # Verify - outputs should differ due to parameter differences
        # We cannot check exact values, but we can check that they're not identical
        assert not np.array_equal(result_default, result_custom)

    def test_preserves_relative_distances(self):
        """Test that UMAP preserves some relative distance relationships."""
        # Create clustered data with clear structure
        n_samples = 40
        cluster1 = np.random.randn(n_samples, 10) + np.array([0] * 10)
        cluster2 = np.random.randn(n_samples, 10) + np.array([10] * 10)
        
        # Combine clusters
        test_matrix = np.vstack([cluster1, cluster2])
        
        # Apply UMAP
        umap_segment = ReduceUMAP(random_state=42)
        reduced_data = list(umap_segment([test_matrix]))[0]
        
        # Verify clusters remain somewhat separated in reduced space
        reduced_cluster1 = reduced_data[:n_samples]
        reduced_cluster2 = reduced_data[n_samples:]
        
        # Calculate mean of each cluster in reduced space
        mean1 = np.mean(reduced_cluster1, axis=0)
        mean2 = np.mean(reduced_cluster2, axis=0)
        
        # Calculate average distance within each cluster
        avg_dist1 = np.mean([np.linalg.norm(x - mean1) for x in reduced_cluster1])
        avg_dist2 = np.mean([np.linalg.norm(x - mean2) for x in reduced_cluster2])
        
        # Calculate distance between cluster means
        between_dist = np.linalg.norm(mean1 - mean2)
        
        # Distance between clusters should be larger than average within-cluster distance
        assert between_dist > avg_dist1
        assert between_dist > avg_dist2
    def test_different_random_states(self):
        """Test that different random states produce different results with sufficiently diverse data."""
        # Create more clearly clustered data to emphasize the effect of randomization
        X, y = make_blobs(n_samples=1000, centers=4, n_features=10, random_state=42, cluster_std=2.0)
        
        # Use extreme random states for stronger differentiation
        # Also force exact calculation with method='exact' to make differences more apparent
        reducer1 = ReduceTSNE(random_state=0, init="random")
        reducer2 = ReduceTSNE(random_state=999, init="random")

        # Transform the data with both reducers
        result1 = list(reducer1.transform([X]))
        result2 = list(reducer2.transform([X]))
        
        # Compare the relative arrangement of points
        # We'll measure distances between points in each result
        # Even if the overall embeddings are similar, the relative distances should differ
        
        # Calculate the pairwise distances for the first 20 points in each embedding
        from scipy.spatial.distance import pdist
        
        # Use a subset of points to make the test faster and more reliable
        dist1 = pdist(result1[0][:20])
        dist2 = pdist(result2[0][:20])
        
        # The distributions of distances should be different
        # Calculate their correlation - it should not be extremely high
        from scipy.stats import pearsonr
        correlation, _ = pearsonr(dist1, dist2)
        
        # The correlation shouldn't be extremely high (e.g., > 0.95)
        # even with correlation, there should be noticeable differences
        assert correlation < 0.95, f"Distance patterns should differ substantially, but correlation is {correlation}"
        
        # Additionally, check that at least some pairs of points have very different 
        # relative distances across the two embeddings
        max_diff_ratio = max(abs(dist1/dist2 - 1))
        assert max_diff_ratio > 0.2, f"Maximum difference in distance ratios should be substantial, got {max_diff_ratio}"

    def test_reproducibility_with_random_state(self):
        """Test that setting random_state produces reproducible results."""
        # Create test data
        test_matrix = np.random.rand(25, 7)  # 25 samples, 7 features
        
        # Run UMAP twice with same random_state
        umap_segment1 = ReduceUMAP(random_state=42)
        umap_segment2 = ReduceUMAP(random_state=42)
        
        result1 = list(umap_segment1([test_matrix]))[0]
        result2 = list(umap_segment2([test_matrix]))[0]
        
        # Results should be identical
        np.testing.assert_array_equal(result1, result2)
        
        # Now with different random_state
        umap_segment3 = ReduceUMAP(random_state=99)
        result3 = list(umap_segment3([test_matrix]))[0]
        
        # Results should be different
        assert not np.array_equal(result1, result3)

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
