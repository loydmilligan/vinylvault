"""
Performance tests for response times and system load.
"""

import pytest
import time
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock


@pytest.mark.performance
@pytest.mark.slow
class TestResponseTimes:
    """Test response time performance requirements."""
    
    def test_index_page_response_time(self, client, authenticated_session, performance_timer):
        """Test index page loads within 2 seconds."""
        performance_timer.start()
        response = client.get('/')
        performance_timer.stop()
        
        assert response.status_code == 200
        assert performance_timer.elapsed() < 2.0, f"Index page took {performance_timer.elapsed():.2f}s"
    
    def test_setup_page_response_time(self, client, performance_timer):
        """Test setup page loads within 2 seconds."""
        performance_timer.start()
        response = client.get('/setup')
        performance_timer.stop()
        
        assert response.status_code == 200
        assert performance_timer.elapsed() < 2.0, f"Setup page took {performance_timer.elapsed():.2f}s"
    
    @patch('app.get_random_album')
    def test_random_page_response_time(self, mock_get_random, client, authenticated_session, performance_timer):
        """Test random album selection within 2 seconds."""
        mock_get_random.return_value = {
            'discogs_id': 123,
            'title': 'Test Album',
            'artist': 'Test Artist',
            'score': 0.85
        }
        
        performance_timer.start()
        response = client.get('/random')
        performance_timer.stop()
        
        assert response.status_code == 200
        assert performance_timer.elapsed() < 2.0, f"Random page took {performance_timer.elapsed():.2f}s"
    
    @patch('app.get_global_client')
    def test_stats_page_response_time(self, mock_get_client, client, authenticated_session, performance_timer):
        """Test stats page loads within 2 seconds."""
        mock_client = Mock()
        mock_client.get_collection_stats.return_value = {
            'total_albums': 1000,
            'total_artists': 500,
            'genres': {'Rock': 300, 'Jazz': 200, 'Electronic': 150},
            'avg_rating': 4.2
        }
        mock_get_client.return_value = mock_client
        
        performance_timer.start()
        response = client.get('/stats')
        performance_timer.stop()
        
        assert response.status_code == 200
        assert performance_timer.elapsed() < 2.0, f"Stats page took {performance_timer.elapsed():.2f}s"
    
    def test_api_albums_response_time(self, client, authenticated_session, performance_timer):
        """Test API albums endpoint response time."""
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.get_recent_albums.return_value = [
                {'discogs_id': i, 'title': f'Album {i}', 'artist': f'Artist {i}'}
                for i in range(100)  # 100 albums
            ]
            mock_get_client.return_value = mock_client
            
            performance_timer.start()
            response = client.get('/api/albums')
            performance_timer.stop()
            
            assert response.status_code == 200
            assert performance_timer.elapsed() < 1.0, f"API albums took {performance_timer.elapsed():.2f}s"
    
    @patch('app.get_random_album')
    def test_api_random_response_time(self, mock_get_random, client, authenticated_session, performance_timer):
        """Test API random endpoint response time."""
        mock_get_random.return_value = {
            'discogs_id': 123,
            'title': 'Random Album',
            'artist': 'Random Artist',
            'score': 0.75
        }
        
        performance_timer.start()
        response = client.get('/api/random')
        performance_timer.stop()
        
        assert response.status_code == 200
        assert performance_timer.elapsed() < 0.5, f"API random took {performance_timer.elapsed():.2f}s"
    
    def test_concurrent_requests_performance(self, client, authenticated_session):
        """Test performance under concurrent load."""
        def make_request():
            start_time = time.time()
            response = client.get('/')
            end_time = time.time()
            return {
                'status_code': response.status_code,
                'response_time': end_time - start_time
            }
        
        # Simulate 10 concurrent users
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [future.result() for future in futures]
        
        # All requests should succeed
        success_count = sum(1 for r in results if r['status_code'] == 200)
        assert success_count >= 8, f"Only {success_count}/10 requests succeeded"
        
        # Average response time should be reasonable
        avg_response_time = sum(r['response_time'] for r in results) / len(results)
        assert avg_response_time < 3.0, f"Average response time {avg_response_time:.2f}s too high"
        
        # No individual request should be extremely slow
        max_response_time = max(r['response_time'] for r in results)
        assert max_response_time < 5.0, f"Slowest request took {max_response_time:.2f}s"
    
    def test_database_query_performance(self, test_db, performance_timer):
        """Test database query performance."""
        # Insert test data
        albums = []
        for i in range(1000):
            albums.append((
                i,
                f'Album {i}',
                f'Artist {i % 100}',
                2000 + (i % 25),
                ['Rock', 'Jazz', 'Electronic'][i % 3],
                (i % 5) + 1
            ))
        
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, albums)
        test_db.commit()
        
        # Test various query patterns
        queries = [
            "SELECT COUNT(*) FROM albums",
            "SELECT * FROM albums ORDER BY user_rating DESC LIMIT 10",
            "SELECT genre, COUNT(*) FROM albums GROUP BY genre",
            "SELECT * FROM albums WHERE artist = 'Artist 50'",
            "SELECT AVG(user_rating) FROM albums"
        ]
        
        for query in queries:
            performance_timer.start()
            cursor = test_db.execute(query)
            results = cursor.fetchall()
            performance_timer.stop()
            
            assert performance_timer.elapsed() < 0.1, f"Query '{query}' took {performance_timer.elapsed():.2f}s"
    
    def test_image_cache_performance(self, test_config, performance_timer):
        """Test image cache lookup performance."""
        from image_cache import ImageCache
        
        cache_dir = test_config.COVERS_DIR
        
        # Create mock cached images
        for i in range(100):
            cache_file = cache_dir / f"test_image_{i}.jpg"
            cache_file.write_bytes(b"fake image data")
        
        cache = ImageCache(cache_dir)
        
        # Test cache lookup performance
        performance_timer.start()
        for i in range(100):
            with patch.object(cache, '_generate_cache_key', return_value=f"test_image_{i}.jpg"):
                cache.get_cached_image_url(f"https://example.com/image_{i}.jpg")
        performance_timer.stop()
        
        # 100 cache lookups should be very fast
        assert performance_timer.elapsed() < 0.5, f"Cache lookups took {performance_timer.elapsed():.2f}s"
    
    def test_random_algorithm_performance(self, test_db, performance_timer):
        """Test random algorithm performance with large collection."""
        # Insert large collection
        albums = []
        for i in range(5000):
            albums.append((
                i,
                f'Album {i}',
                f'Artist {i % 500}',
                2000 + (i % 25),
                ['Rock', 'Jazz', 'Electronic', 'Pop', 'Classical'][i % 5],
                (i % 5) + 1
            ))
        
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, albums)
        test_db.commit()
        
        # Test random selection performance
        with patch('random_algorithm.get_random_album') as mock_get_random:
            mock_get_random.return_value = {
                'discogs_id': 1234,
                'title': 'Selected Album',
                'score': 0.85
            }
            
            performance_timer.start()
            for _ in range(10):  # 10 selections
                mock_get_random()
            performance_timer.stop()
            
            # Should be very fast even with large collection
            assert performance_timer.elapsed() < 1.0, f"Random selections took {performance_timer.elapsed():.2f}s"
    
    def test_memory_usage_under_load(self, client, authenticated_session):
        """Test memory usage doesn't grow excessively under load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Make many requests
        for i in range(50):
            response = client.get('/')
            assert response.status_code == 200
            
            # Check memory every 10 requests
            if i % 10 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_growth = current_memory - initial_memory
                
                # Memory shouldn't grow excessively (allow 50MB growth)
                assert memory_growth < 50, f"Memory grew by {memory_growth:.1f}MB after {i} requests"
    
    def test_static_file_serving_performance(self, client, performance_timer):
        """Test static file serving performance."""
        static_files = [
            '/static/style.css',
            '/static/app.js',
            '/static/vinyl-icon.svg'
        ]
        
        for static_file in static_files:
            performance_timer.start()
            response = client.get(static_file)
            performance_timer.stop()
            
            # Static files should be served very quickly
            assert response.status_code in [200, 404]  # 404 if file doesn't exist
            if response.status_code == 200:
                assert performance_timer.elapsed() < 0.1, f"Static file {static_file} took {performance_timer.elapsed():.2f}s"
    
    def test_database_connection_pool_performance(self, test_config):
        """Test database connection performance under concurrent access."""
        import sqlite3
        import threading
        
        results = []
        
        def database_worker():
            start_time = time.time()
            conn = sqlite3.connect(str(test_config.DATABASE_PATH))
            cursor = conn.execute("SELECT COUNT(*) FROM albums")
            result = cursor.fetchone()
            conn.close()
            end_time = time.time()
            
            results.append({
                'result': result,
                'time': end_time - start_time
            })
        
        # Create multiple threads accessing database
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=database_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All operations should complete quickly
        assert len(results) == 10
        avg_time = sum(r['time'] for r in results) / len(results)
        assert avg_time < 0.1, f"Average DB connection time {avg_time:.2f}s too high"
    
    def test_startup_time_performance(self, test_config, performance_timer):
        """Test application startup time."""
        from app import create_app
        
        performance_timer.start()
        app = create_app(test_config)
        performance_timer.stop()
        
        # App creation should be fast
        assert performance_timer.elapsed() < 3.0, f"App startup took {performance_timer.elapsed():.2f}s"
        assert app is not None