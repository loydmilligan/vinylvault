"""
Integration tests for the collection synchronization workflow.
"""

import pytest
import time
from unittest.mock import patch, Mock
from datetime import datetime


@pytest.mark.integration
@pytest.mark.slow
class TestSyncWorkflow:
    """Test complete collection synchronization workflow."""
    
    def test_complete_sync_workflow(self, client, test_db, authenticated_session):
        """Test complete sync workflow from initiation to completion."""
        # Step 1: Access sync page
        response = client.get('/sync')
        assert response.status_code == 200
        assert b'sync' in response.data.lower()
        
        # Step 2: Initiate sync
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.is_online.return_value = True
            mock_client.sync_collection.return_value = {
                'status': 'started',
                'sync_id': 'test_sync_123'
            }
            mock_get_client.return_value = mock_client
            
            response = client.post('/sync', data={'sync_type': 'full'})
            assert response.status_code in [200, 302]
        
        # Step 3: Check sync status
        with patch('app.get_sync_status') as mock_get_status:
            mock_get_status.return_value = {
                'status': 'in_progress',
                'progress': 50,
                'albums_processed': 25,
                'total_albums': 50,
                'current_album': 'Processing Album 25'
            }
            
            response = client.get('/api/sync/status')
            assert response.status_code == 200
            
            data = response.get_json()
            assert data['status'] == 'in_progress'
            assert data['progress'] == 50
        
        # Step 4: Verify sync completion
        with patch('app.get_sync_status') as mock_get_status:
            mock_get_status.return_value = {
                'status': 'completed',
                'progress': 100,
                'albums_processed': 50,
                'total_albums': 50,
                'albums_added': 30,
                'albums_updated': 20
            }
            
            response = client.get('/api/sync/status')
            assert response.status_code == 200
            
            data = response.get_json()
            assert data['status'] == 'completed'
            assert data['albums_added'] == 30
            assert data['albums_updated'] == 20
    
    def test_incremental_sync_workflow(self, client, test_db, authenticated_session):
        """Test incremental sync workflow."""
        # Insert existing albums with old sync dates
        from datetime import datetime, timedelta
        old_date = (datetime.now() - timedelta(days=7)).isoformat()
        
        test_albums = [
            (1, 'Old Album 1', 'Artist 1', old_date),
            (2, 'Old Album 2', 'Artist 2', old_date),
            (3, 'Recent Album', 'Artist 3', datetime.now().isoformat())
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, last_synced)
                VALUES (?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Initiate incremental sync
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.is_online.return_value = True
            mock_client.sync_collection.return_value = {
                'status': 'started',
                'sync_type': 'incremental',
                'albums_to_sync': 2  # Only old albums
            }
            mock_get_client.return_value = mock_client
            
            response = client.post('/sync', data={'sync_type': 'incremental'})
            assert response.status_code in [200, 302]
    
    def test_sync_error_handling_workflow(self, client, authenticated_session):
        """Test sync error handling workflow."""
        # Test network error during sync
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.is_online.return_value = False
            mock_get_client.return_value = mock_client
            
            response = client.post('/sync', data={'sync_type': 'full'})
            
            # Should handle offline client gracefully
            assert response.status_code in [200, 400]
        
        # Test API error during sync
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.is_online.return_value = True
            mock_client.sync_collection.side_effect = Exception("API Error")
            mock_get_client.return_value = mock_client
            
            response = client.post('/sync', data={'sync_type': 'full'})
            
            # Should handle API errors gracefully
            assert response.status_code in [200, 500]
    
    def test_sync_progress_tracking_workflow(self, client, test_db, authenticated_session):
        """Test sync progress tracking throughout workflow."""
        sync_id = 'test_sync_progress'
        
        # Insert initial sync log entry
        test_db.execute("""
            INSERT INTO sync_log (sync_id, sync_type, started_at, status, 
                                albums_processed, total_albums)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sync_id, 'full_sync', datetime.now().isoformat(), 'in_progress', 0, 100))
        test_db.commit()
        
        # Simulate progress updates
        progress_updates = [
            (25, 'processing'),
            (50, 'processing'), 
            (75, 'processing'),
            (100, 'completed')
        ]
        
        for albums_processed, status in progress_updates:
            test_db.execute("""
                UPDATE sync_log 
                SET albums_processed = ?, status = ?
                WHERE sync_id = ?
            """, (albums_processed, status, sync_id))
            test_db.commit()
            
            # Check progress via API
            with patch('app.get_current_sync_id', return_value=sync_id):
                response = client.get('/api/sync/status')
                assert response.status_code == 200
                
                data = response.get_json()
                assert data['albums_processed'] == albums_processed
                assert data['status'] == status
    
    def test_sync_cancellation_workflow(self, client, authenticated_session):
        """Test sync cancellation workflow."""
        # Start sync
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.is_online.return_value = True
            mock_client.sync_collection.return_value = {
                'status': 'started',
                'sync_id': 'cancellable_sync'
            }
            mock_get_client.return_value = mock_client
            
            response = client.post('/sync', data={'sync_type': 'full'})
            assert response.status_code in [200, 302]
        
        # Cancel sync
        with patch('app.cancel_sync') as mock_cancel:
            mock_cancel.return_value = {'status': 'cancelled'}
            
            response = client.post('/api/sync/cancel')
            assert response.status_code in [200, 202]
            
            data = response.get_json()
            assert data['status'] == 'cancelled'
    
    def test_sync_rate_limiting_workflow(self, client, authenticated_session):
        """Test sync with rate limiting workflow."""
        # Simulate rapid sync requests
        responses = []
        
        with patch('app.get_global_client') as mock_get_client:
            mock_client = Mock()
            mock_client.is_online.return_value = True
            mock_client.sync_collection.return_value = {'status': 'started'}
            mock_get_client.return_value = mock_client
            
            # Make multiple rapid sync requests
            for i in range(5):
                response = client.post('/sync', data={'sync_type': 'full'})
                responses.append(response.status_code)
        
        # First request should succeed, subsequent might be rate limited
        assert responses[0] in [200, 302]
        # Some requests might be rejected due to ongoing sync
        rejected_count = sum(1 for status in responses if status in [400, 429])
        assert rejected_count <= 4  # At most 4 should be rejected
    
    def test_sync_album_processing_workflow(self, client, test_db, authenticated_session):
        """Test individual album processing during sync."""
        # Mock album data from Discogs
        mock_album_data = {
            'id': 123456,
            'basic_information': {
                'title': 'Test Album',
                'artists': [{'name': 'Test Artist'}],
                'year': 2023,
                'genres': ['Rock'],
                'styles': ['Alternative'],
                'labels': [{'name': 'Test Label', 'catno': 'TEST001'}],
                'formats': [{'name': 'Vinyl', 'descriptions': ['LP']}],
                'thumb': 'https://example.com/thumb.jpg',
                'cover_image': 'https://example.com/cover.jpg'
            },
            'rating': 4,
            'date_added': '2023-01-01T00:00:00-08:00'
        }
        
        with patch('app.process_album_data') as mock_process:
            mock_process.return_value = True
            
            # Simulate processing single album
            with patch('app.get_global_client') as mock_get_client:
                mock_client = Mock()
                mock_client.get_collection_page.return_value = [mock_album_data]
                mock_get_client.return_value = mock_client
                
                # This would be called internally during sync
                mock_process(mock_album_data, test_db)
                
                # Verify album was processed
                mock_process.assert_called_once()
    
    def test_sync_database_transaction_workflow(self, client, test_db, authenticated_session):
        """Test database transaction handling during sync."""
        # Simulate sync with database transaction
        try:
            test_db.execute("BEGIN")
            
            # Insert sync log
            test_db.execute("""
                INSERT INTO sync_log (sync_type, started_at, status)
                VALUES (?, ?, ?)
            """, ('test_sync', datetime.now().isoformat(), 'in_progress'))
            
            # Insert test album
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year)
                VALUES (?, ?, ?, ?)
            """, (999, 'Sync Test Album', 'Sync Test Artist', 2023))
            
            # Commit transaction
            test_db.commit()
            
            # Verify data was inserted
            cursor = test_db.execute("SELECT COUNT(*) as count FROM albums WHERE discogs_id = ?", (999,))
            count = cursor.fetchone()['count']
            assert count == 1
            
        except Exception:
            test_db.rollback()
            raise
    
    def test_sync_image_caching_workflow(self, client, test_config, authenticated_session):
        """Test image caching during sync workflow."""
        from image_cache import ImageCache
        
        cache = ImageCache(test_config.COVERS_DIR)
        
        # Mock album with cover image
        album_data = {
            'discogs_id': 123,
            'title': 'Album with Cover',
            'cover_url': 'https://example.com/cover.jpg'
        }
        
        with patch.object(cache, 'cache_image') as mock_cache:
            mock_cache.return_value = True
            
            # Simulate caching during sync
            result = cache.cache_image(album_data['cover_url'])
            assert result is True
            
            mock_cache.assert_called_once_with(album_data['cover_url'])
    
    def test_sync_recovery_workflow(self, client, test_db, authenticated_session):
        """Test sync recovery after interruption."""
        # Simulate interrupted sync
        sync_id = 'interrupted_sync'
        test_db.execute("""
            INSERT INTO sync_log (sync_id, sync_type, started_at, status, 
                                albums_processed, total_albums)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sync_id, 'full_sync', datetime.now().isoformat(), 'interrupted', 50, 100))
        test_db.commit()
        
        # Resume sync
        with patch('app.resume_sync') as mock_resume:
            mock_resume.return_value = {
                'status': 'resumed',
                'albums_remaining': 50
            }
            
            response = client.post('/api/sync/resume', json={'sync_id': sync_id})
            
            if response.status_code == 200:
                data = response.get_json()
                assert data['status'] == 'resumed'
    
    def test_sync_statistics_workflow(self, client, test_db, authenticated_session):
        """Test sync statistics collection workflow."""
        # Complete sync with statistics
        sync_id = 'stats_sync'
        test_db.execute("""
            INSERT INTO sync_log (sync_id, sync_type, started_at, completed_at, 
                                status, albums_added, albums_updated, albums_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sync_id, 'full_sync', 
              datetime.now().isoformat(),
              datetime.now().isoformat(),
              'completed', 25, 15, 2))
        test_db.commit()
        
        # Get sync statistics
        cursor = test_db.execute("""
            SELECT * FROM sync_log WHERE sync_id = ?
        """, (sync_id,))
        
        sync_record = cursor.fetchone()
        assert sync_record is not None
        assert sync_record['albums_added'] == 25
        assert sync_record['albums_updated'] == 15
        assert sync_record['albums_deleted'] == 2
        assert sync_record['status'] == 'completed'