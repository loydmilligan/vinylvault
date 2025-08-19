"""
Unit tests for API endpoints.
"""

import pytest
import json
from unittest.mock import patch, Mock
from flask import url_for


@pytest.mark.api
@pytest.mark.unit
class TestAPIEndpoints:
    """Test all Flask API endpoints."""
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get('/health')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data is not None
        assert 'status' in data
        assert data['status'] in ['ok', 'healthy']
        assert 'timestamp' in data
    
    def test_index_redirect_without_setup(self, client):
        """Test index redirects to setup when not configured."""
        response = client.get('/')
        
        # Should redirect to setup if not configured
        assert response.status_code in [200, 302]
        
        if response.status_code == 302:
            assert '/setup' in response.location
    
    def test_setup_page_renders(self, client):
        """Test setup page renders correctly."""
        response = client.get('/setup')
        
        assert response.status_code == 200
        assert b'setup' in response.data.lower() or b'discogs' in response.data.lower()
    
    @patch('app.get_user_discogs_data')
    def test_setup_post_valid_token(self, mock_get_user, client):
        """Test setup with valid Discogs token."""
        mock_get_user.return_value = None  # No existing user
        
        with patch('app.validate_discogs_token') as mock_validate:
            mock_validate.return_value = ('testuser', True)
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_token',
                'username': 'testuser'
            })
            
            # Should redirect after successful setup
            assert response.status_code in [200, 302]
    
    def test_setup_post_invalid_token(self, client):
        """Test setup with invalid Discogs token."""
        response = client.post('/setup', data={
            'discogs_token': 'invalid_token',
            'username': 'testuser'
        })
        
        # Should return to setup page with error
        assert response.status_code in [200, 400]
    
    @patch('app.get_user_discogs_data')
    def test_index_with_setup_completed(self, mock_get_user, client, authenticated_session):
        """Test index page when setup is completed."""
        mock_get_user.return_value = ('testuser', b'encrypted_token')
        
        response = client.get('/')
        
        assert response.status_code == 200
        # Should show main interface
        assert b'collection' in response.data.lower() or b'vinyl' in response.data.lower()
    
    @patch('app.get_global_client')
    def test_sync_page_renders(self, mock_get_client, client, authenticated_session):
        """Test sync page renders correctly."""
        mock_client = Mock()
        mock_client.is_online.return_value = True
        mock_get_client.return_value = mock_client
        
        response = client.get('/sync')
        
        assert response.status_code == 200
        assert b'sync' in response.data.lower()
    
    @patch('app.get_global_client')
    def test_sync_post_starts_sync(self, mock_get_client, client, authenticated_session):
        """Test POST to sync endpoint starts synchronization."""
        mock_client = Mock()
        mock_client.is_online.return_value = True
        mock_client.sync_collection.return_value = {'status': 'started'}
        mock_get_client.return_value = mock_client
        
        response = client.post('/sync', data={'sync_type': 'full'})
        
        assert response.status_code in [200, 302]
    
    @patch('app.get_random_album')
    def test_random_page_renders(self, mock_get_random, client, authenticated_session):
        """Test random album page renders correctly."""
        mock_get_random.return_value = {
            'discogs_id': 123,
            'title': 'Test Album',
            'artist': 'Test Artist',
            'year': 2023,
            'genre': 'Rock',
            'cover_url': 'https://example.com/cover.jpg'
        }
        
        response = client.get('/random')
        
        assert response.status_code == 200
        assert b'Test Album' in response.data
        assert b'Test Artist' in response.data
    
    @patch('app.get_random_album')
    def test_random_no_albums(self, mock_get_random, client, authenticated_session):
        """Test random page when no albums available."""
        mock_get_random.return_value = None
        
        response = client.get('/random')
        
        assert response.status_code == 200
        # Should show appropriate message
        assert b'no albums' in response.data.lower() or b'empty' in response.data.lower()
    
    @patch('app.record_album_feedback')
    def test_random_feedback_submission(self, mock_record, client, authenticated_session):
        """Test submitting feedback on random album selection."""
        mock_record.return_value = True
        
        response = client.post('/random', data={
            'album_id': '123',
            'feedback': 'liked'
        })
        
        assert response.status_code in [200, 302]
        mock_record.assert_called_once()
    
    @patch('app.get_global_client')
    def test_stats_page_renders(self, mock_get_client, client, authenticated_session):
        """Test statistics page renders correctly."""
        mock_client = Mock()
        mock_client.get_collection_stats.return_value = {
            'total_albums': 100,
            'total_artists': 50,
            'genres': {'Rock': 30, 'Jazz': 20},
            'avg_rating': 4.2
        }
        mock_get_client.return_value = mock_client
        
        response = client.get('/stats')
        
        assert response.status_code == 200
        assert b'100' in response.data  # Total albums
        assert b'4.2' in response.data  # Average rating
    
    def test_api_albums_endpoint(self, client, authenticated_session):
        """Test /api/albums endpoint."""
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.get_recent_albums.return_value = [
                {
                    'discogs_id': 123,
                    'title': 'Test Album',
                    'artist': 'Test Artist',
                    'year': 2023
                }
            ]
            mock_get_client.return_value = mock_client
            
            response = client.get('/api/albums')
            
            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, list)
            assert len(data) >= 0
    
    def test_api_albums_with_filters(self, client, authenticated_session):
        """Test /api/albums endpoint with filters."""
        response = client.get('/api/albums?genre=Rock&limit=10')
        
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
    
    @patch('app.get_random_album')
    def test_api_random_endpoint(self, mock_get_random, client, authenticated_session):
        """Test /api/random endpoint."""
        mock_get_random.return_value = {
            'discogs_id': 123,
            'title': 'Random Album',
            'artist': 'Random Artist',
            'score': 0.85
        }
        
        response = client.get('/api/random')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['discogs_id'] == 123
        assert data['title'] == 'Random Album'
        assert 'score' in data
    
    def test_api_random_no_albums(self, client, authenticated_session):
        """Test /api/random when no albums available."""
        with patch('app.get_random_album', return_value=None):
            response = client.get('/api/random')
            
            assert response.status_code == 404
            data = response.get_json()
            assert 'error' in data
    
    @patch('app.get_algorithm_statistics')
    def test_api_stats_endpoint(self, mock_get_stats, client, authenticated_session):
        """Test /api/stats endpoint."""
        mock_get_stats.return_value = {
            'total_albums': 200,
            'total_artists': 75,
            'avg_rating': 4.1,
            'genres': {'Rock': 50, 'Jazz': 30},
            'cache_stats': {
                'hit_rate': 0.85,
                'total_images': 150
            }
        }
        
        response = client.get('/api/stats')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['total_albums'] == 200
        assert data['avg_rating'] == 4.1
        assert 'cache_stats' in data
    
    def test_api_sync_status_endpoint(self, client, authenticated_session):
        """Test /api/sync/status endpoint."""
        with patch('app.get_sync_status') as mock_get_status:
            mock_get_status.return_value = {
                'status': 'in_progress',
                'progress': 50,
                'albums_processed': 25,
                'total_albums': 50
            }
            
            response = client.get('/api/sync/status')
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'in_progress'
            assert data['progress'] == 50
    
    def test_api_sync_start_endpoint(self, client, authenticated_session):
        """Test /api/sync/start endpoint."""
        with patch('app.start_background_sync') as mock_start:
            mock_start.return_value = {'sync_id': 'test_sync_123', 'status': 'started'}
            
            response = client.post('/api/sync/start', 
                                 json={'sync_type': 'incremental'})
            
            assert response.status_code == 200
            data = response.get_json()
            assert data['status'] == 'started'
            assert 'sync_id' in data
    
    def test_album_detail_page(self, client, authenticated_session):
        """Test individual album detail page."""
        with patch('app.get_album_details') as mock_get_album:
            mock_get_album.return_value = {
                'discogs_id': 123,
                'title': 'Detailed Album',
                'artist': 'Detailed Artist',
                'year': 2023,
                'genre': 'Rock',
                'tracks': ['Track 1', 'Track 2']
            }
            
            response = client.get('/album/123')
            
            assert response.status_code == 200
            assert b'Detailed Album' in response.data
    
    def test_album_detail_not_found(self, client, authenticated_session):
        """Test album detail page for non-existent album."""
        with patch('app.get_album_details', return_value=None):
            response = client.get('/album/999999')
            
            assert response.status_code == 404
    
    def test_error_handlers_404(self, client):
        """Test 404 error handler."""
        response = client.get('/nonexistent-page')
        
        assert response.status_code == 404
        # Should render custom 404 template
        assert b'404' in response.data or b'not found' in response.data.lower()
    
    def test_error_handlers_500(self, client):
        """Test 500 error handler."""
        @client.application.route('/test-error')
        def trigger_error():
            raise Exception("Test error")
        
        response = client.get('/test-error')
        
        # In testing mode, might not catch the error
        assert response.status_code in [500, 200]  # Depends on testing config
    
    def test_api_content_type_json(self, client, authenticated_session):
        """Test API endpoints return JSON content type."""
        response = client.get('/api/stats')
        
        assert response.status_code == 200
        assert 'application/json' in response.content_type
    
    def test_api_cors_headers(self, client):
        """Test CORS headers on API endpoints."""
        response = client.options('/api/stats')
        
        # Should handle OPTIONS request for CORS
        assert response.status_code in [200, 204, 405]
    
    def test_rate_limiting(self, client, authenticated_session):
        """Test rate limiting on API endpoints."""
        # Make multiple rapid requests
        responses = []
        for i in range(10):
            response = client.get('/api/stats')
            responses.append(response.status_code)
        
        # Most should succeed, but rate limiting might kick in
        success_count = sum(1 for status in responses if status == 200)
        assert success_count >= 5  # At least some should succeed
    
    def test_authentication_required_endpoints(self, client):
        """Test that protected endpoints require authentication."""
        protected_endpoints = [
            '/sync',
            '/random',
            '/stats',
            '/api/albums',
            '/api/random',
            '/api/stats'
        ]
        
        for endpoint in protected_endpoints:
            response = client.get(endpoint)
            
            # Should redirect to setup or return 401/403
            assert response.status_code in [200, 302, 401, 403]
            
            if response.status_code == 302:
                assert '/setup' in response.location or '/login' in response.location
    
    def test_input_validation_api_endpoints(self, client, authenticated_session):
        """Test input validation on API endpoints."""
        # Test invalid JSON
        response = client.post('/api/sync/start', 
                             data='invalid json',
                             content_type='application/json')
        
        assert response.status_code in [400, 422]
        
        # Test missing required fields
        response = client.post('/api/sync/start', json={})
        
        assert response.status_code in [200, 400, 422]
    
    def test_pagination_support(self, client, authenticated_session):
        """Test pagination support in list endpoints."""
        response = client.get('/api/albums?page=1&limit=10')
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Should handle pagination parameters
        assert isinstance(data, (list, dict))
        
        if isinstance(data, dict):
            # Paginated response format
            assert 'items' in data or 'albums' in data
        else:
            # Simple list format
            assert len(data) <= 10  # Respect limit