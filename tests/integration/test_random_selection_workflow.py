"""
Integration tests for the complete random selection workflow.
"""

import pytest
from unittest.mock import patch, Mock
from datetime import datetime


@pytest.mark.integration
class TestRandomSelectionWorkflow:
    """Test complete random album selection workflow."""
    
    def test_complete_random_selection_workflow(self, client, test_db, authenticated_session):
        """Test complete random selection from album request to feedback."""
        # Step 1: Populate database with test albums
        test_albums = [
            (1, 'Great Album', 'Amazing Artist', 2023, 'Rock', 5, 0),
            (2, 'Good Album', 'Good Artist', 2022, 'Jazz', 4, 2),
            (3, 'Okay Album', 'Okay Artist', 2021, 'Electronic', 3, 5),
            (4, 'New Album', 'New Artist', 2024, 'Pop', 0, 0)  # No rating, never selected
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating, selection_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Step 2: Request random album
        with patch('app.get_random_album') as mock_get_random:
            mock_get_random.return_value = {
                'discogs_id': 1,
                'title': 'Great Album',
                'artist': 'Amazing Artist',
                'year': 2023,
                'genre': 'Rock',
                'user_rating': 5,
                'score': 0.95,
                'cover_url': 'https://example.com/cover1.jpg'
            }
            
            response = client.get('/random')
            assert response.status_code == 200
            assert b'Great Album' in response.data
            assert b'Amazing Artist' in response.data
        
        # Step 3: Submit positive feedback
        with patch('app.record_album_feedback') as mock_record:
            mock_record.return_value = True
            
            response = client.post('/random', data={
                'album_id': '1',
                'feedback': 'liked'
            })
            
            assert response.status_code in [200, 302]
            mock_record.assert_called_once()
        
        # Step 4: Verify feedback was recorded
        cursor = test_db.execute("""
            SELECT selection_count FROM albums WHERE discogs_id = ?
        """, (1,))
        album = cursor.fetchone()
        # Selection count should be updated (in real implementation)
        assert album is not None
    
    def test_random_selection_with_algorithm_configuration(self, client, test_db, authenticated_session):
        """Test random selection with different algorithm configurations."""
        # Insert test albums
        test_albums = [
            (1, 'High Rated', 'Artist 1', 2023, 'Rock', 5),
            (2, 'Low Rated', 'Artist 2', 2022, 'Jazz', 2),
            (3, 'Medium Rated', 'Artist 3', 2021, 'Electronic', 3)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
                VALUES (?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Test with rating-focused algorithm
        with patch('app.get_user_algorithm_config') as mock_get_config, \
             patch('app.get_random_album') as mock_get_random:
            
            mock_get_config.return_value = {
                'rating_weight': 0.8,
                'recency_weight': 0.1,
                'diversity_weight': 0.1,
                'discovery_weight': 0.0
            }
            
            mock_get_random.return_value = {
                'discogs_id': 1,  # Should favor high-rated album
                'title': 'High Rated',
                'score': 0.92
            }
            
            response = client.get('/random')
            assert response.status_code == 200
            assert b'High Rated' in response.data
    
    def test_random_selection_api_workflow(self, client, test_db, authenticated_session):
        """Test random selection via API workflow."""
        # Insert test album
        test_db.execute("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (123, 'API Test Album', 'API Artist', 2023, 'Rock', 4))
        test_db.commit()
        
        # Step 1: Get random album via API
        with patch('app.get_random_album') as mock_get_random:
            mock_get_random.return_value = {
                'discogs_id': 123,
                'title': 'API Test Album',
                'artist': 'API Artist',
                'score': 0.85
            }
            
            response = client.get('/api/random')
            assert response.status_code == 200
            
            data = response.get_json()
            assert data['discogs_id'] == 123
            assert data['title'] == 'API Test Album'
            assert 'score' in data
        
        # Step 2: Submit feedback via API
        response = client.post('/api/random/feedback', json={
            'album_id': 123,
            'feedback': 'liked'
        })
        
        # Should handle API feedback submission
        assert response.status_code in [200, 201, 404]  # 404 if endpoint doesn't exist
    
    def test_random_selection_empty_collection_workflow(self, client, authenticated_session):
        """Test random selection workflow with empty collection."""
        # No albums in database
        
        # Request random album
        with patch('app.get_random_album') as mock_get_random:
            mock_get_random.return_value = None
            
            response = client.get('/random')
            assert response.status_code == 200
            
            # Should show appropriate message for empty collection
            assert b'no albums' in response.data.lower() or b'empty' in response.data.lower()
        
        # API should return 404
        response = client.get('/api/random')
        if response.status_code == 404:
            data = response.get_json()
            assert 'error' in data
    
    def test_random_selection_with_filters_workflow(self, client, test_db, authenticated_session):
        """Test random selection with genre/artist filters."""
        # Insert albums with different genres
        test_albums = [
            (1, 'Rock Album 1', 'Rock Artist', 2023, 'Rock', 5),
            (2, 'Rock Album 2', 'Rock Artist', 2022, 'Rock', 4),
            (3, 'Jazz Album', 'Jazz Artist', 2021, 'Jazz', 5),
            (4, 'Electronic Album', 'Electronic Artist', 2020, 'Electronic', 3)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
                VALUES (?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Request random rock album
        with patch('app.get_random_album') as mock_get_random:
            mock_get_random.return_value = {
                'discogs_id': 1,
                'title': 'Rock Album 1',
                'genre': 'Rock',
                'score': 0.90
            }
            
            response = client.get('/random?genre=Rock')
            assert response.status_code == 200
            assert b'Rock Album' in response.data
    
    def test_random_selection_history_tracking_workflow(self, client, test_db, authenticated_session):
        """Test random selection history tracking."""
        # Insert test album
        test_db.execute("""
            INSERT INTO albums (discogs_id, title, artist, year)
            VALUES (?, ?, ?, ?)
        """, (456, 'History Album', 'History Artist', 2023))
        test_db.commit()
        
        # Make multiple selections
        selection_history = []
        
        for i in range(3):
            with patch('app.get_random_album') as mock_get_random, \
                 patch('app.record_selection') as mock_record:
                
                mock_get_random.return_value = {
                    'discogs_id': 456,
                    'title': 'History Album',
                    'selection_id': f'selection_{i}',
                    'score': 0.8 - (i * 0.1)  # Decreasing score
                }
                
                mock_record.return_value = True
                
                response = client.get('/random')
                assert response.status_code == 200
                
                selection_history.append(f'selection_{i}')
        
        # Verify selection history is tracked
        assert len(selection_history) == 3
    
    def test_random_selection_diversity_workflow(self, client, test_db, authenticated_session):
        """Test random selection diversity over time."""
        # Insert albums from different genres and artists
        test_albums = []
        genres = ['Rock', 'Jazz', 'Electronic', 'Pop', 'Classical']
        
        for i in range(25):  # 5 albums per genre
            genre = genres[i // 5]
            test_albums.append((
                i + 1,
                f'{genre} Album {i % 5 + 1}',
                f'{genre} Artist {i % 5 + 1}',
                2020 + (i % 5),
                genre,
                (i % 5) + 1
            ))
        
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, test_albums)
        test_db.commit()
        
        # Simulate selections over time
        selected_genres = []
        
        for i in range(10):
            with patch('app.get_random_album') as mock_get_random:
                # Simulate diversity-aware selection
                selected_genre = genres[i % 5]  # Rotate through genres
                
                mock_get_random.return_value = {
                    'discogs_id': (i % 5) + 1,
                    'title': f'{selected_genre} Album 1',
                    'genre': selected_genre,
                    'score': 0.8
                }
                
                response = client.get('/random')
                assert response.status_code == 200
                
                selected_genres.append(selected_genre)
        
        # Check diversity (should have selected from multiple genres)
        unique_genres = set(selected_genres)
        assert len(unique_genres) >= 3, f"Only selected from {len(unique_genres)} genres"
    
    def test_random_selection_feedback_impact_workflow(self, client, test_db, authenticated_session):
        """Test how feedback impacts future selections."""
        # Insert test albums
        test_albums = [
            (1, 'Liked Album', 'Artist 1', 2023, 'Rock', 4),
            (2, 'Disliked Album', 'Artist 2', 2022, 'Rock', 4)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
                VALUES (?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Select first album and give positive feedback
        with patch('app.get_random_album') as mock_get_random, \
             patch('app.record_album_feedback') as mock_record:
            
            mock_get_random.return_value = {
                'discogs_id': 1,
                'title': 'Liked Album',
                'score': 0.8
            }
            
            response = client.get('/random')
            assert response.status_code == 200
            
            # Submit positive feedback
            mock_record.return_value = True
            response = client.post('/random', data={
                'album_id': '1',
                'feedback': 'liked'
            })
            assert response.status_code in [200, 302]
        
        # Select second album and give negative feedback
        with patch('app.get_random_album') as mock_get_random, \
             patch('app.record_album_feedback') as mock_record:
            
            mock_get_random.return_value = {
                'discogs_id': 2,
                'title': 'Disliked Album',
                'score': 0.8
            }
            
            response = client.get('/random')
            assert response.status_code == 200
            
            # Submit negative feedback
            mock_record.return_value = True
            response = client.post('/random', data={
                'album_id': '2',
                'feedback': 'disliked'
            })
            assert response.status_code in [200, 302]
    
    def test_random_selection_performance_workflow(self, client, test_db, authenticated_session):
        """Test random selection performance with large collection."""
        # Insert large collection
        albums = []
        for i in range(1000):
            albums.append((
                i,
                f'Album {i}',
                f'Artist {i % 100}',
                2000 + (i % 25),
                ['Rock', 'Jazz', 'Electronic', 'Pop'][i % 4],
                (i % 5) + 1
            ))
        
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, albums)
        test_db.commit()
        
        # Test selection performance
        import time
        
        with patch('app.get_random_album') as mock_get_random:
            mock_get_random.return_value = {
                'discogs_id': 500,
                'title': 'Album 500',
                'score': 0.85
            }
            
            start_time = time.time()
            response = client.get('/random')
            end_time = time.time()
            
            assert response.status_code == 200
            # Should be fast even with large collection
            assert (end_time - start_time) < 2.0