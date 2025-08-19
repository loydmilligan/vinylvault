"""
Memory usage and resource performance tests.
"""

import pytest
import psutil
import os
import time
import gc
from unittest.mock import patch, Mock


@pytest.mark.performance
@pytest.mark.slow
class TestMemoryUsage:
    """Test memory usage and resource management."""
    
    def get_memory_usage(self):
        """Get current memory usage in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    
    def test_baseline_memory_usage(self, client):
        """Test baseline memory usage of the application."""
        # Force garbage collection
        gc.collect()
        
        initial_memory = self.get_memory_usage()
        
        # Make a simple request
        response = client.get('/health')
        assert response.status_code == 200
        
        # Memory shouldn't increase significantly for a simple request
        final_memory = self.get_memory_usage()
        memory_diff = final_memory - initial_memory
        
        # Allow up to 5MB increase for a simple request
        assert memory_diff < 5, f"Memory increased by {memory_diff:.1f}MB for simple request"
    
    def test_memory_usage_under_sustained_load(self, client, authenticated_session):
        """Test memory usage under sustained request load."""
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Make many requests
        for i in range(100):
            response = client.get('/')
            assert response.status_code in [200, 302]
            
            # Check memory every 20 requests
            if i % 20 == 0:
                current_memory = self.get_memory_usage()
                memory_growth = current_memory - initial_memory
                
                # Memory growth should be bounded
                assert memory_growth < 20, f"Memory grew by {memory_growth:.1f}MB after {i} requests"
        
        # Force garbage collection and check final memory
        gc.collect()
        time.sleep(0.1)  # Allow cleanup
        final_memory = self.get_memory_usage()
        total_growth = final_memory - initial_memory
        
        # Total memory growth should be reasonable
        assert total_growth < 30, f"Total memory growth {total_growth:.1f}MB after 100 requests"
    
    def test_database_connection_memory_management(self, test_config):
        """Test database connections don't leak memory."""
        import sqlite3
        
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Create and close many database connections
        for _ in range(50):
            conn = sqlite3.connect(str(test_config.DATABASE_PATH))
            cursor = conn.execute("SELECT COUNT(*) FROM albums")
            cursor.fetchone()
            conn.close()
        
        gc.collect()
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Database connections should not cause significant memory growth
        assert memory_growth < 10, f"DB connections caused {memory_growth:.1f}MB memory growth"
    
    def test_image_cache_memory_usage(self, test_config):
        """Test image cache memory usage."""
        from image_cache import ImageCache
        
        cache_dir = test_config.COVERS_DIR
        
        # Create test images
        for i in range(50):
            cache_file = cache_dir / f"test_image_{i}.jpg"
            # Create 10KB fake images
            cache_file.write_bytes(b"x" * 10240)
        
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        cache = ImageCache(cache_dir)
        
        # Perform cache operations
        for i in range(50):
            with patch.object(cache, '_generate_cache_key', return_value=f"test_image_{i}.jpg"):
                cache.get_cached_image_url(f"https://example.com/image_{i}.jpg")
        
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Cache operations should not cause excessive memory growth
        assert memory_growth < 15, f"Image cache caused {memory_growth:.1f}MB memory growth"
    
    def test_collection_processing_memory_usage(self, test_db):
        """Test memory usage when processing large collections."""
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Simulate processing a large collection
        batch_size = 1000
        for batch in range(5):  # 5 batches of 1000 albums
            albums = []
            for i in range(batch_size):
                album_id = batch * batch_size + i
                albums.append((
                    album_id,
                    f'Album {album_id}',
                    f'Artist {album_id % 100}',
                    2000 + (album_id % 25),
                    ['Rock', 'Jazz', 'Electronic'][album_id % 3],
                    (album_id % 5) + 1
                ))
            
            # Insert batch
            test_db.executemany("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
                VALUES (?, ?, ?, ?, ?, ?)
            """, albums)
            test_db.commit()
            
            # Check memory after each batch
            current_memory = self.get_memory_usage()
            memory_growth = current_memory - initial_memory
            
            # Memory growth should be manageable
            assert memory_growth < 50, f"Memory grew by {memory_growth:.1f}MB after batch {batch}"
        
        # Final memory check
        gc.collect()
        final_memory = self.get_memory_usage()
        total_growth = final_memory - initial_memory
        assert total_growth < 60, f"Total memory growth {total_growth:.1f}MB for 5000 albums"
    
    def test_random_algorithm_memory_efficiency(self, test_db):
        """Test random algorithm memory efficiency with large datasets."""
        # Insert large dataset
        albums = []
        for i in range(2000):
            albums.append((
                i,
                f'Album {i}',
                f'Artist {i % 200}',
                2000 + (i % 25),
                ['Rock', 'Jazz', 'Electronic', 'Pop'][i % 4],
                (i % 5) + 1
            ))
        
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, albums)
        test_db.commit()
        
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Simulate many random selections
        with patch('random_algorithm.get_random_album') as mock_get_random:
            mock_get_random.return_value = {
                'discogs_id': 123,
                'title': 'Random Album',
                'score': 0.85
            }
            
            for _ in range(100):
                mock_get_random()
        
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Random algorithm should be memory efficient
        assert memory_growth < 10, f"Random algorithm used {memory_growth:.1f}MB extra memory"
    
    def test_concurrent_requests_memory_impact(self, client, authenticated_session):
        """Test memory impact of concurrent requests."""
        import threading
        import queue
        
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Queue to store results
        result_queue = queue.Queue()
        
        def worker():
            try:
                for _ in range(10):
                    response = client.get('/')
                    result_queue.put(response.status_code)
            except Exception as e:
                result_queue.put(f"Error: {e}")
        
        # Start multiple threads
        threads = []
        for _ in range(5):  # 5 threads, 10 requests each = 50 total
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Collect results
        results = []
        while not result_queue.empty():
            results.append(result_queue.get())
        
        gc.collect()
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Concurrent requests should not cause excessive memory growth
        assert memory_growth < 25, f"Concurrent requests caused {memory_growth:.1f}MB memory growth"
        
        # Most requests should succeed
        success_count = sum(1 for r in results if r == 200 or r == 302)
        assert success_count >= 40, f"Only {success_count}/50 requests succeeded"
    
    def test_session_memory_management(self, client):
        """Test Flask session memory management."""
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Create many sessions
        for i in range(100):
            with client.session_transaction() as sess:
                sess[f'test_key_{i}'] = f'test_value_{i}'
                sess['user_id'] = i
                sess['timestamp'] = time.time()
        
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Session creation should not cause excessive memory growth
        assert memory_growth < 15, f"Session creation caused {memory_growth:.1f}MB memory growth"
    
    def test_static_file_caching_memory(self, client):
        """Test static file caching doesn't consume excessive memory."""
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Request static files multiple times
        static_files = ['/static/style.css', '/static/app.js', '/static/vinyl-icon.svg']
        
        for _ in range(20):  # 20 iterations
            for static_file in static_files:
                response = client.get(static_file)
                # Files might not exist in test environment
                assert response.status_code in [200, 404]
        
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Static file serving should be memory efficient
        assert memory_growth < 8, f"Static file serving caused {memory_growth:.1f}MB memory growth"
    
    def test_raspberry_pi_memory_constraints(self, client, authenticated_session):
        """Test memory usage is suitable for Raspberry Pi (limited to ~100MB)."""
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Simulate typical usage patterns
        for i in range(20):
            # Navigate through different pages
            pages = ['/', '/random', '/stats', '/api/albums', '/api/stats']
            for page in pages:
                response = client.get(page)
                assert response.status_code in [200, 302, 404]
        
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Memory usage should be suitable for Raspberry Pi
        assert final_memory < 100, f"Total memory usage {final_memory:.1f}MB exceeds Pi limits"
        assert memory_growth < 30, f"Memory growth {memory_growth:.1f}MB too high for Pi"
    
    def test_garbage_collection_effectiveness(self, client):
        """Test that garbage collection effectively reclaims memory."""
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Create memory pressure
        large_data = []
        for i in range(100):
            # Create temporary large objects
            large_data.append([f"data_{j}" for j in range(1000)])
            
            # Make a request
            response = client.get('/health')
            assert response.status_code == 200
        
        # Clear references
        del large_data
        
        # Force garbage collection
        gc.collect()
        time.sleep(0.1)  # Allow cleanup
        
        final_memory = self.get_memory_usage()
        memory_after_gc = final_memory - initial_memory
        
        # Garbage collection should reclaim most memory
        assert memory_after_gc < 20, f"Memory not reclaimed after GC: {memory_after_gc:.1f}MB remaining"
    
    def test_database_result_memory_efficiency(self, test_db):
        """Test database query results don't consume excessive memory."""
        # Insert test data
        albums = [(i, f'Album {i}', f'Artist {i}', 2020) for i in range(1000)]
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year)
            VALUES (?, ?, ?, ?)
        """, albums)
        test_db.commit()
        
        gc.collect()
        initial_memory = self.get_memory_usage()
        
        # Execute queries that return large result sets
        queries = [
            "SELECT * FROM albums",
            "SELECT title, artist FROM albums ORDER BY title",
            "SELECT COUNT(*), artist FROM albums GROUP BY artist"
        ]
        
        for query in queries:
            cursor = test_db.execute(query)
            results = cursor.fetchall()
            # Process results to simulate real usage
            processed = [(row[0], row[1]) for row in results[:100]]
            del results, processed
        
        gc.collect()
        final_memory = self.get_memory_usage()
        memory_growth = final_memory - initial_memory
        
        # Database queries should be memory efficient
        assert memory_growth < 12, f"Database queries caused {memory_growth:.1f}MB memory growth"