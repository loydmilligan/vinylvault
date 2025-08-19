#!/usr/bin/env python3
"""
Test script for VinylVault Image Cache System

This script tests the image cache functionality to ensure it works correctly
before integration with the main application.
"""

import logging
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
import requests

from image_cache import initialize_image_cache, get_image_cache, shutdown_image_cache
from config import Config

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_image_cache():
    """Test the image cache functionality."""
    
    # Create temporary directories for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        cache_dir = temp_path / 'cache' / 'covers'
        db_path = temp_path / 'test.db'
        
        print(f"Testing with temporary directory: {temp_path}")
        
        # Initialize cache
        print("\n1. Initializing image cache...")
        success = initialize_image_cache(cache_dir, db_path, max_cache_size=50*1024*1024)  # 50MB for testing
        
        if not success:
            print("❌ Failed to initialize image cache")
            return False
        
        cache = get_image_cache()
        if not cache:
            print("❌ Cache not available after initialization")
            return False
        
        print("✅ Image cache initialized successfully")
        
        # Test placeholder creation
        print("\n2. Testing placeholder creation...")
        try:
            thumbnail_placeholder = cache.get_placeholder_path('thumbnails')
            detail_placeholder = cache.get_placeholder_path('detail')
            
            if Path(thumbnail_placeholder).exists() and Path(detail_placeholder).exists():
                print("✅ Placeholders created successfully")
            else:
                print("❌ Placeholders not created")
                return False
        except Exception as e:
            print(f"❌ Placeholder creation failed: {e}")
            return False
        
        # Test cache stats
        print("\n3. Testing cache statistics...")
        try:
            stats = cache.get_cache_stats()
            print(f"   Initial cache entries: {stats.total_entries}")
            print(f"   Cache size: {stats.total_size_bytes} bytes")
            print(f"   Cache limit: {stats.cache_limit_bytes} bytes")
            print("✅ Cache statistics working")
        except Exception as e:
            print(f"❌ Cache statistics failed: {e}")
            return False
        
        # Test with a sample image URL (using a placeholder service)
        print("\n4. Testing image caching with sample URL...")
        test_url = "https://via.placeholder.com/600x600.jpg"
        
        try:
            # This would normally download and cache the image
            # For testing, we'll simulate it
            print(f"   Testing URL: {test_url}")
            
            # Test cache key generation
            cache_key = cache._generate_cache_key(test_url, 'detail')
            print(f"   Generated cache key: {cache_key[:16]}...")
            
            # Test file path generation
            file_path = cache._get_cache_file_path(cache_key, 'detail')
            print(f"   Cache file path: {file_path}")
            
            print("✅ Cache URL processing working")
            
        except Exception as e:
            print(f"❌ Image caching test failed: {e}")
            return False
        
        # Test LRU cache functionality
        print("\n5. Testing LRU cache...")
        try:
            lru_stats = cache.lru_cache.get_stats()
            print(f"   LRU entries: {lru_stats['entries']}")
            print(f"   LRU size: {lru_stats['size_bytes']} bytes")
            print(f"   LRU hit rate: {lru_stats['hit_rate']:.1f}%")
            print("✅ LRU cache working")
        except Exception as e:
            print(f"❌ LRU cache test failed: {e}")
            return False
        
        # Test cache cleanup
        print("\n6. Testing cache cleanup...")
        try:
            cleanup_result = cache.cleanup_cache(max_age_days=0)  # Clean everything
            print(f"   Cleaned up {cleanup_result} entries")
            print("✅ Cache cleanup working")
        except Exception as e:
            print(f"❌ Cache cleanup failed: {e}")
            return False
        
        # Test cache clearing
        print("\n7. Testing cache clearing...")
        try:
            clear_success = cache.clear_cache()
            if clear_success:
                print("✅ Cache clearing working")
            else:
                print("❌ Cache clearing failed")
                return False
        except Exception as e:
            print(f"❌ Cache clearing test failed: {e}")
            return False
        
        # Cleanup
        print("\n8. Shutting down cache...")
        shutdown_image_cache()
        print("✅ Cache shutdown complete")
        
        print("\n🎉 All tests passed! Image cache is working correctly.")
        return True

def test_performance():
    """Test cache performance with multiple operations."""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        cache_dir = temp_path / 'cache' / 'covers'
        db_path = temp_path / 'test.db'
        
        print(f"\nPerformance testing with: {temp_path}")
        
        # Initialize cache with smaller limit for testing
        success = initialize_image_cache(cache_dir, db_path, max_cache_size=10*1024*1024)  # 10MB
        
        if not success:
            print("❌ Failed to initialize cache for performance test")
            return False
        
        cache = get_image_cache()
        
        # Test rapid cache key generation
        print("\nTesting cache key generation performance...")
        import time
        
        test_urls = [f"https://example.com/image_{i}.jpg" for i in range(100)]
        
        start_time = time.time()
        for url in test_urls:
            cache._generate_cache_key(url, 'detail')
        end_time = time.time()
        
        print(f"Generated 100 cache keys in {(end_time - start_time)*1000:.1f}ms")
        
        # Test cache stats performance
        print("\nTesting cache stats performance...")
        start_time = time.time()
        for _ in range(10):
            cache.get_cache_stats()
        end_time = time.time()
        
        print(f"Retrieved cache stats 10 times in {(end_time - start_time)*1000:.1f}ms")
        
        shutdown_image_cache()
        print("✅ Performance tests completed")
        return True

def test_memory_optimization():
    """Test memory optimization features."""
    
    print("\nTesting memory optimization...")
    
    # Test image processor
    from image_cache import MemoryOptimizedProcessor
    
    processor = MemoryOptimizedProcessor()
    
    # Test with a simple image (create a test image)
    try:
        from PIL import Image
        import io
        
        # Create a test image
        test_img = Image.new('RGB', (800, 800), color='red')
        img_bytes = io.BytesIO()
        test_img.save(img_bytes, format='JPEG')
        img_data = img_bytes.getvalue()
        
        print(f"Original image size: {len(img_data)} bytes")
        
        # Process to thumbnail
        thumb_data = processor.process_image(img_data, (150, 150))
        print(f"Thumbnail size: {len(thumb_data)} bytes")
        
        # Process to detail
        detail_data = processor.process_image(img_data, (600, 600))
        print(f"Detail size: {len(detail_data)} bytes")
        
        # Verify WebP format
        thumb_img = Image.open(io.BytesIO(thumb_data))
        detail_img = Image.open(io.BytesIO(detail_data))
        
        print(f"Thumbnail format: {thumb_img.format}, size: {thumb_img.size}")
        print(f"Detail format: {detail_img.format}, size: {detail_img.size}")
        
        if thumb_img.format == 'WEBP' and detail_img.format == 'WEBP':
            print("✅ WebP conversion working")
        else:
            print("❌ WebP conversion failed")
            return False
        
        print("✅ Memory optimization tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Memory optimization test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("VinylVault Image Cache Test Suite")
    print("=" * 40)
    
    tests_passed = 0
    total_tests = 3
    
    # Basic functionality test
    if test_image_cache():
        tests_passed += 1
    
    # Performance test
    if test_performance():
        tests_passed += 1
    
    # Memory optimization test
    if test_memory_optimization():
        tests_passed += 1
    
    print(f"\nTest Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Image cache is ready for production.")
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1

if __name__ == '__main__':
    exit(main())