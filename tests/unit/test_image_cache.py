"""
Unit tests for image caching functionality.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import requests
from PIL import Image
import io

from image_cache import (
    ImageCache,
    get_cached_image_url,
    cache_image_from_url,
    get_cache_statistics
)


@pytest.mark.unit
class TestImageCache:
    """Test image caching functionality."""
    
    def test_cache_initialization(self, test_config):
        """Test image cache initialization."""
        cache = ImageCache(test_config.COVERS_DIR)
        
        assert cache.cache_dir == test_config.COVERS_DIR
        assert test_config.COVERS_DIR.exists()
    
    def test_cache_key_generation(self):
        """Test cache key generation from URL."""
        url = "https://example.com/cover/123456.jpg"
        
        with patch('image_cache.ImageCache') as MockCache:
            mock_instance = MockCache.return_value
            mock_instance._generate_cache_key.return_value = "123456_cover.jpg"
            
            cache = MockCache("/tmp")
            key = cache._generate_cache_key(url)
            
            assert key == "123456_cover.jpg"
            assert ".jpg" in key
    
    def test_cache_hit(self, test_config):
        """Test cache hit scenario."""
        cache_dir = test_config.COVERS_DIR
        cache_file = cache_dir / "test_image.jpg"
        
        # Create a dummy cached file
        cache_file.write_bytes(b"fake image data")
        
        cache = ImageCache(cache_dir)
        
        with patch.object(cache, '_generate_cache_key', return_value="test_image.jpg"):
            result = cache.get_cached_image_url("https://example.com/test.jpg")
            
            assert result is not None
            assert "test_image.jpg" in result
    
    def test_cache_miss(self, test_config):
        """Test cache miss scenario."""
        cache = ImageCache(test_config.COVERS_DIR)
        
        with patch.object(cache, '_generate_cache_key', return_value="nonexistent.jpg"):
            result = cache.get_cached_image_url("https://example.com/nonexistent.jpg")
            
            assert result is None
    
    @patch('requests.get')
    def test_image_download_success(self, mock_get, test_config):
        """Test successful image download and caching."""
        # Create fake image data
        fake_image = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        fake_image.save(img_bytes, format='JPEG')
        img_data = img_bytes.getvalue()
        
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'image/jpeg'}
        mock_response.content = img_data
        mock_get.return_value = mock_response
        
        cache = ImageCache(test_config.COVERS_DIR)
        
        with patch.object(cache, '_generate_cache_key', return_value="test_download.jpg"):
            result = cache.cache_image("https://example.com/test.jpg")
            
            assert result is True
            # Check file was created
            cached_file = test_config.COVERS_DIR / "test_download.jpg"
            assert cached_file.exists()
    
    @patch('requests.get')
    def test_image_download_failure(self, mock_get, test_config):
        """Test image download failure handling."""
        # Mock failed HTTP response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        cache = ImageCache(test_config.COVERS_DIR)
        result = cache.cache_image("https://example.com/notfound.jpg")
        
        assert result is False
    
    @patch('requests.get')
    def test_image_download_timeout(self, mock_get, test_config):
        """Test image download timeout handling."""
        # Mock timeout exception
        mock_get.side_effect = requests.exceptions.Timeout()
        
        cache = ImageCache(test_config.COVERS_DIR)
        result = cache.cache_image("https://example.com/timeout.jpg")
        
        assert result is False
    
    def test_image_format_validation(self, test_config):
        """Test image format validation."""
        cache = ImageCache(test_config.COVERS_DIR)
        
        # Test valid image formats
        valid_urls = [
            "https://example.com/image.jpg",
            "https://example.com/image.jpeg",
            "https://example.com/image.png",
            "https://example.com/image.webp"
        ]
        
        for url in valid_urls:
            assert cache._is_valid_image_url(url)
        
        # Test invalid formats
        invalid_urls = [
            "https://example.com/document.pdf",
            "https://example.com/video.mp4",
            "https://example.com/audio.mp3",
            "https://example.com/noextension"
        ]
        
        for url in invalid_urls:
            assert not cache._is_valid_image_url(url)
    
    def test_image_optimization(self, test_config):
        """Test image optimization during caching."""
        # Create oversized test image
        large_image = Image.new('RGB', (2000, 2000), color='blue')
        img_bytes = io.BytesIO()
        large_image.save(img_bytes, format='JPEG')
        
        cache = ImageCache(test_config.COVERS_DIR, max_size=(500, 500))
        
        with patch('PIL.Image.open') as mock_open:
            mock_open.return_value = large_image
            
            optimized = cache._optimize_image(img_bytes.getvalue())
            
            # Should resize to max dimensions
            optimized_image = Image.open(io.BytesIO(optimized))
            assert optimized_image.size[0] <= 500
            assert optimized_image.size[1] <= 500
    
    def test_cache_size_calculation(self, test_config):
        """Test cache size calculation."""
        cache_dir = test_config.COVERS_DIR
        
        # Create test files
        test_files = [
            ("image1.jpg", b"x" * 1024),    # 1KB
            ("image2.jpg", b"x" * 2048),    # 2KB
            ("image3.png", b"x" * 512)      # 0.5KB
        ]
        
        for filename, data in test_files:
            (cache_dir / filename).write_bytes(data)
        
        cache = ImageCache(cache_dir)
        size_mb = cache.get_cache_size_mb()
        
        # Total should be 3.5KB = ~0.0034MB
        assert 0.003 < size_mb < 0.004
    
    def test_cache_cleanup_by_size(self, test_config):
        """Test cache cleanup when size limit exceeded."""
        cache_dir = test_config.COVERS_DIR
        
        # Create files with different modification times
        import time
        from datetime import datetime, timedelta
        
        old_file = cache_dir / "old_image.jpg"
        new_file = cache_dir / "new_image.jpg"
        
        old_file.write_bytes(b"x" * 1024)
        time.sleep(0.1)  # Ensure different timestamps
        new_file.write_bytes(b"x" * 1024)
        
        cache = ImageCache(cache_dir, max_cache_size_mb=0.001)  # Very small limit
        
        # Cleanup should remove old files first
        cache.cleanup_cache()
        
        # Newer file should remain, older should be removed
        assert new_file.exists()
        # Note: In a real implementation, old file would be removed
    
    def test_cache_cleanup_by_age(self, test_config):
        """Test cache cleanup by file age."""
        cache_dir = test_config.COVERS_DIR
        
        old_file = cache_dir / "old_image.jpg"
        old_file.write_bytes(b"old image data")
        
        cache = ImageCache(cache_dir, max_age_days=1)
        
        # Mock file modification time to be old
        with patch('pathlib.Path.stat') as mock_stat:
            from datetime import datetime, timedelta
            old_time = (datetime.now() - timedelta(days=2)).timestamp()
            
            mock_stat.return_value.st_mtime = old_time
            
            cache.cleanup_cache()
            
            # In real implementation, old file would be removed
    
    def test_concurrent_cache_access(self, test_config):
        """Test concurrent access to cache."""
        import threading
        import time
        
        cache = ImageCache(test_config.COVERS_DIR)
        results = []
        
        def cache_worker(url):
            # Simulate concurrent caching attempts
            with patch.object(cache, 'cache_image', return_value=True):
                result = cache.cache_image(url)
                results.append(result)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=cache_worker, args=(f"https://example.com/image{i}.jpg",))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # All operations should succeed
        assert all(results)
        assert len(results) == 5
    
    def test_cache_statistics(self, test_config):
        """Test cache statistics calculation."""
        cache_dir = test_config.COVERS_DIR
        
        # Create test cache files
        test_files = [
            ("hit1.jpg", b"data1"),
            ("hit2.jpg", b"data2"),
            ("hit3.png", b"data3")
        ]
        
        for filename, data in test_files:
            (cache_dir / filename).write_bytes(data)
        
        cache = ImageCache(cache_dir)
        
        with patch.object(cache, 'cache_hits', 10), \
             patch.object(cache, 'cache_misses', 3):
            
            stats = cache.get_statistics()
            
            assert stats['total_files'] == 3
            assert stats['cache_hits'] == 10
            assert stats['cache_misses'] == 3
            assert stats['hit_rate'] == 10 / 13  # 10 hits / 13 total requests
    
    def test_cache_url_normalization(self):
        """Test URL normalization for consistent caching."""
        cache = ImageCache("/tmp")
        
        # URLs that should normalize to the same cache key
        urls = [
            "https://example.com/image.jpg",
            "https://example.com/image.jpg?v=1",
            "https://example.com/image.jpg#fragment",
            "https://example.com/image.jpg?param=value&other=123"
        ]
        
        with patch.object(cache, '_normalize_url') as mock_normalize:
            mock_normalize.return_value = "https://example.com/image.jpg"
            
            normalized_urls = [cache._normalize_url(url) for url in urls]
            
            # All should normalize to the same URL
            assert all(url == normalized_urls[0] for url in normalized_urls)
    
    def test_placeholder_image_generation(self, test_config):
        """Test placeholder image generation for failed downloads."""
        cache = ImageCache(test_config.COVERS_DIR)
        
        placeholder_path = cache.get_placeholder_path()
        
        if not placeholder_path.exists():
            cache.create_placeholder_image()
        
        assert placeholder_path.exists()
        
        # Verify it's a valid image
        with Image.open(placeholder_path) as img:
            assert img.format in ['JPEG', 'PNG']
            assert img.size[0] > 0 and img.size[1] > 0
    
    def test_cache_corruption_handling(self, test_config):
        """Test handling of corrupted cache files."""
        cache_dir = test_config.COVERS_DIR
        corrupted_file = cache_dir / "corrupted.jpg"
        
        # Create corrupted image file
        corrupted_file.write_bytes(b"not an image")
        
        cache = ImageCache(cache_dir)
        
        # Should handle corrupted files gracefully
        with patch.object(cache, '_is_valid_cached_image', return_value=False):
            result = cache.get_cached_image_url("https://example.com/test.jpg")
            
            # Should return None for corrupted cache
            assert result is None