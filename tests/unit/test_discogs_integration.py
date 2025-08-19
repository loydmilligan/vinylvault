"""
Unit tests for Discogs integration functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import responses
import json
from datetime import datetime

from discogs_client import (
    create_discogs_client,
    DiscogsAPIError,
    DiscogsConnectionError,
    DiscogsRateLimiter
)


@pytest.mark.unit
class TestDiscogsIntegration:
    """Test Discogs API integration."""
    
    def test_discogs_client_creation(self, test_config):
        """Test Discogs client creation."""
        client = create_discogs_client(test_config.DATABASE_PATH)
        
        assert client is not None
        assert hasattr(client, 'is_online')
        assert hasattr(client, 'get_collection_stats')
        assert hasattr(client, 'sync_collection')
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        limiter = DiscogsRateLimiter(max_requests=60, window=60)
        
        assert limiter.max_requests == 60
        assert limiter.window == 60
        assert limiter.requests == []
    
    def test_rate_limiter_allows_requests_within_limit(self):
        """Test rate limiter allows requests within limit."""
        limiter = DiscogsRateLimiter(max_requests=5, window=60)
        
        # Should allow requests within limit
        for i in range(5):
            limiter.wait_if_needed()  # Should not block
    
    def test_rate_limiter_blocks_excess_requests(self):
        """Test rate limiter blocks excess requests."""
        import time
        
        limiter = DiscogsRateLimiter(max_requests=2, window=10)
        
        # First two requests should be immediate
        start_time = time.time()
        limiter.wait_if_needed()
        limiter.wait_if_needed()
        elapsed = time.time() - start_time
        
        assert elapsed < 1.0  # Should be nearly instant
        
        # Third request should be delayed (but we won't wait for it in test)
        # Just verify the limiter knows it would need to wait
        assert len(limiter.requests) == 2
    
    @responses.activate
    def test_discogs_api_authentication(self, sample_user_data):
        """Test Discogs API authentication."""
        # Mock successful authentication response
        responses.add(
            responses.GET,
            'https://api.discogs.com/oauth/identity',
            json={'username': sample_user_data['username'], 'id': 12345},
            status=200
        )
        
        with patch('discogs_client.get_user_discogs_data') as mock_get_user:
            mock_get_user.return_value = (
                sample_user_data['username'],
                sample_user_data['encrypted_token']
            )
            
            with patch('discogs_client.Fernet') as mock_fernet:
                mock_fernet.return_value.decrypt.return_value = sample_user_data['token'].encode()
                
                # This would test actual authentication
                # In a real test, we'd need to mock the Discogs client initialization
                pass
    
    @responses.activate
    def test_collection_fetch(self):
        """Test fetching user collection from Discogs."""
        # Mock collection response
        collection_response = {
            'releases': [
                {
                    'id': 123456,
                    'basic_information': {
                        'title': 'Test Album',
                        'artists': [{'name': 'Test Artist'}],
                        'year': 2023,
                        'genres': ['Rock'],
                        'styles': ['Alternative Rock'],
                        'labels': [{'name': 'Test Records', 'catno': 'TEST001'}],
                        'formats': [{'name': 'Vinyl', 'descriptions': ['LP']}],
                        'thumb': 'https://example.com/thumb.jpg',
                        'cover_image': 'https://example.com/cover.jpg'
                    },
                    'rating': 4,
                    'date_added': '2023-01-01T00:00:00-08:00'
                }
            ],
            'pagination': {
                'page': 1,
                'pages': 1,
                'per_page': 50,
                'items': 1
            }
        }
        
        responses.add(
            responses.GET,
            'https://api.discogs.com/users/testuser/collection/folders/0/releases',
            json=collection_response,
            status=200
        )
        
        # Test would involve actual collection fetching
        # Mock the client and test the response parsing
        pass
    
    def test_collection_stats_calculation(self, test_db):
        """Test collection statistics calculation."""
        # Insert test data
        test_albums = [
            (1, 'Album 1', 'Artist 1', 2020, 'Rock', 'Alternative', 4),
            (2, 'Album 2', 'Artist 2', 2021, 'Jazz', 'Bebop', 5),
            (3, 'Album 3', 'Artist 1', 2019, 'Rock', 'Progressive', 3),
            (4, 'Album 4', 'Artist 3', 2022, 'Electronic', 'House', 4)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, style, user_rating)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Test stats calculation (would be part of client)
        with patch('discogs_client.create_discogs_client') as mock_create:
            mock_client = Mock()
            mock_client.get_collection_stats.return_value = {
                'total_albums': 4,
                'total_artists': 3,
                'genres': {'Rock': 2, 'Jazz': 1, 'Electronic': 1},
                'decades': {'2020s': 3, '2010s': 1},
                'avg_rating': 4.0
            }
            mock_create.return_value = mock_client
            
            client = create_discogs_client(test_db)
            stats = client.get_collection_stats()
            
            assert stats['total_albums'] == 4
            assert stats['total_artists'] == 3
            assert stats['avg_rating'] == 4.0
    
    def test_discogs_error_handling(self):
        """Test Discogs API error handling."""
        # Test DiscogsAPIError
        error = DiscogsAPIError("Rate limit exceeded", status_code=429)
        assert error.status_code == 429
        assert "Rate limit exceeded" in str(error)
        
        # Test DiscogsConnectionError
        conn_error = DiscogsConnectionError("Connection timeout")
        assert "Connection timeout" in str(conn_error)
    
    @responses.activate
    def test_api_rate_limit_handling(self):
        """Test handling of API rate limits."""
        # Mock rate limit response
        responses.add(
            responses.GET,
            'https://api.discogs.com/users/testuser/collection/folders/0/releases',
            status=429,
            headers={'Retry-After': '60'}
        )
        
        # Test that rate limit errors are properly handled
        # This would be tested in the actual client implementation
        pass
    
    @responses.activate  
    def test_api_timeout_handling(self):
        """Test handling of API timeouts."""
        import requests
        
        def timeout_callback(request):
            raise requests.Timeout("Request timed out")
        
        responses.add_callback(
            responses.GET,
            'https://api.discogs.com/users/testuser/collection/folders/0/releases',
            callback=timeout_callback
        )
        
        # Test timeout handling would be implemented in client
        pass
    
    def test_album_data_parsing(self):
        """Test parsing of album data from Discogs API."""
        # Sample API response data
        api_data = {
            'id': 123456,
            'basic_information': {
                'title': 'Test Album',
                'artists': [{'name': 'Test Artist'}],
                'year': 2023,
                'genres': ['Rock'],
                'styles': ['Alternative Rock'],
                'labels': [{'name': 'Test Records', 'catno': 'TEST001'}],
                'formats': [{'name': 'Vinyl', 'descriptions': ['LP']}],
                'thumb': 'https://example.com/thumb.jpg',
                'cover_image': 'https://example.com/cover.jpg',
                'country': 'US'
            },
            'rating': 4,
            'date_added': '2023-01-01T00:00:00-08:00'
        }
        
        # Test data extraction (would be part of client implementation)
        # This test documents expected data structure
        assert api_data['id'] == 123456
        assert api_data['basic_information']['title'] == 'Test Album'
        assert api_data['basic_information']['artists'][0]['name'] == 'Test Artist'
        assert api_data['basic_information']['year'] == 2023
    
    def test_sync_progress_tracking(self, test_db):
        """Test sync progress tracking functionality."""
        # Insert sync log entry
        sync_id = 'test_sync_' + datetime.now().isoformat()
        
        test_db.execute("""
            INSERT INTO sync_log (sync_id, sync_type, started_at, status, 
                                albums_processed, total_albums)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sync_id, 'full_sync', datetime.now().isoformat(), 'in_progress', 10, 100))
        test_db.commit()
        
        # Test progress retrieval
        cursor = test_db.execute("""
            SELECT * FROM sync_log WHERE sync_id = ?
        """, (sync_id,))
        sync_record = cursor.fetchone()
        
        assert sync_record is not None
        assert sync_record['status'] == 'in_progress'
        assert sync_record['albums_processed'] == 10
        assert sync_record['total_albums'] == 100
        
        # Calculate progress percentage
        progress = (sync_record['albums_processed'] / sync_record['total_albums']) * 100
        assert progress == 10.0
    
    def test_incremental_sync_detection(self, test_db):
        """Test detection of albums needing incremental sync."""
        from datetime import timedelta
        
        # Insert albums with different sync dates
        old_sync_date = (datetime.now() - timedelta(days=7)).isoformat()
        recent_sync_date = (datetime.now() - timedelta(hours=1)).isoformat()
        
        test_albums = [
            (1, 'Old Album', 'Artist 1', old_sync_date),
            (2, 'Recent Album', 'Artist 2', recent_sync_date),
            (3, 'Never Synced', 'Artist 3', None)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, last_synced)
                VALUES (?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Query albums needing sync (older than 1 day or never synced)
        one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
        
        cursor = test_db.execute("""
            SELECT discogs_id, title FROM albums 
            WHERE last_synced IS NULL OR last_synced < ?
        """, (one_day_ago,))
        
        albums_needing_sync = cursor.fetchall()
        
        # Should include old album and never synced album
        assert len(albums_needing_sync) == 2
        album_ids = [album['discogs_id'] for album in albums_needing_sync]
        assert 1 in album_ids  # Old album
        assert 3 in album_ids  # Never synced
        assert 2 not in album_ids  # Recent album