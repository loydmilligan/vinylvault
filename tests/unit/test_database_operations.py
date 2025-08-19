"""
Unit tests for database operations.
"""

import pytest
import sqlite3
from datetime import datetime
from unittest.mock import patch

from config import Config


@pytest.mark.unit
class TestDatabaseOperations:
    """Test database CRUD operations."""
    
    def test_user_data_storage(self, test_db, sample_user_data):
        """Test storing and retrieving user data."""
        # Insert user data
        test_db.execute("""
            INSERT INTO users (username, encrypted_token, setup_completed, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            sample_user_data['username'],
            sample_user_data['encrypted_token'],
            sample_user_data['setup_completed'],
            datetime.now().isoformat()
        ))
        test_db.commit()
        
        # Retrieve user data
        cursor = test_db.execute("SELECT * FROM users WHERE username = ?", 
                                (sample_user_data['username'],))
        user = cursor.fetchone()
        
        assert user is not None
        assert user['username'] == sample_user_data['username']
        assert user['setup_completed'] == sample_user_data['setup_completed']
    
    def test_album_insertion(self, test_db, sample_album_data):
        """Test album data insertion."""
        test_db.execute("""
            INSERT INTO albums (
                discogs_id, title, artist, year, genre, style, label, catno,
                format, country, thumb_url, cover_url, rating, user_rating,
                notes, date_added, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sample_album_data['discogs_id'],
            sample_album_data['title'],
            sample_album_data['artist'],
            sample_album_data['year'],
            sample_album_data['genre'],
            sample_album_data['style'],
            sample_album_data['label'],
            sample_album_data['catno'],
            sample_album_data['format'],
            sample_album_data['country'],
            sample_album_data['thumb_url'],
            sample_album_data['cover_url'],
            sample_album_data['rating'],
            sample_album_data['user_rating'],
            sample_album_data['notes'],
            sample_album_data['date_added'],
            sample_album_data['last_synced']
        ))
        test_db.commit()
        
        # Verify insertion
        cursor = test_db.execute("SELECT * FROM albums WHERE discogs_id = ?", 
                                (sample_album_data['discogs_id'],))
        album = cursor.fetchone()
        
        assert album is not None
        assert album['title'] == sample_album_data['title']
        assert album['artist'] == sample_album_data['artist']
        assert album['year'] == sample_album_data['year']
    
    def test_album_update(self, test_db, sample_album_data):
        """Test album data updates."""
        # Insert initial data
        test_db.execute("""
            INSERT INTO albums (discogs_id, title, artist, rating, user_rating)
            VALUES (?, ?, ?, ?, ?)
        """, (
            sample_album_data['discogs_id'],
            sample_album_data['title'],
            sample_album_data['artist'],
            sample_album_data['rating'],
            sample_album_data['user_rating']
        ))
        test_db.commit()
        
        # Update rating
        new_rating = 5
        test_db.execute("""
            UPDATE albums SET user_rating = ?, last_synced = ?
            WHERE discogs_id = ?
        """, (new_rating, datetime.now().isoformat(), sample_album_data['discogs_id']))
        test_db.commit()
        
        # Verify update
        cursor = test_db.execute("SELECT user_rating FROM albums WHERE discogs_id = ?", 
                                (sample_album_data['discogs_id'],))
        album = cursor.fetchone()
        
        assert album['user_rating'] == new_rating
    
    def test_album_deletion(self, test_db, sample_album_data):
        """Test album deletion."""
        # Insert album
        test_db.execute("""
            INSERT INTO albums (discogs_id, title, artist)
            VALUES (?, ?, ?)
        """, (
            sample_album_data['discogs_id'],
            sample_album_data['title'],
            sample_album_data['artist']
        ))
        test_db.commit()
        
        # Delete album
        test_db.execute("DELETE FROM albums WHERE discogs_id = ?", 
                       (sample_album_data['discogs_id'],))
        test_db.commit()
        
        # Verify deletion
        cursor = test_db.execute("SELECT * FROM albums WHERE discogs_id = ?", 
                                (sample_album_data['discogs_id'],))
        album = cursor.fetchone()
        
        assert album is None
    
    def test_collection_statistics(self, test_db):
        """Test collection statistics queries."""
        # Insert test data
        test_albums = [
            (1, 'Album 1', 'Artist 1', 2020, 'Rock', 4),
            (2, 'Album 2', 'Artist 2', 2021, 'Jazz', 5),
            (3, 'Album 3', 'Artist 1', 2019, 'Rock', 3),
            (4, 'Album 4', 'Artist 3', 2022, 'Electronic', 4)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
                VALUES (?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        # Test total count
        cursor = test_db.execute("SELECT COUNT(*) as count FROM albums")
        total = cursor.fetchone()['count']
        assert total == 4
        
        # Test genre distribution
        cursor = test_db.execute("""
            SELECT genre, COUNT(*) as count 
            FROM albums 
            GROUP BY genre 
            ORDER BY count DESC
        """)
        genres = cursor.fetchall()
        
        assert len(genres) == 3
        assert genres[0]['genre'] == 'Rock'
        assert genres[0]['count'] == 2
        
        # Test artist count
        cursor = test_db.execute("SELECT COUNT(DISTINCT artist) as count FROM albums")
        artist_count = cursor.fetchone()['count']
        assert artist_count == 3
        
        # Test average rating
        cursor = test_db.execute("SELECT AVG(user_rating) as avg_rating FROM albums")
        avg_rating = cursor.fetchone()['avg_rating']
        assert avg_rating == 4.0
    
    def test_sync_log_operations(self, test_db):
        """Test sync log functionality."""
        # Insert sync log entry
        test_db.execute("""
            INSERT INTO sync_log (sync_type, started_at, completed_at, status, 
                                albums_added, albums_updated, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            'full_sync',
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            'completed',
            10,
            5,
            None
        ))
        test_db.commit()
        
        # Retrieve sync log
        cursor = test_db.execute("""
            SELECT * FROM sync_log 
            ORDER BY started_at DESC 
            LIMIT 1
        """)
        log_entry = cursor.fetchone()
        
        assert log_entry is not None
        assert log_entry['sync_type'] == 'full_sync'
        assert log_entry['status'] == 'completed'
        assert log_entry['albums_added'] == 10
        assert log_entry['albums_updated'] == 5
    
    def test_random_cache_operations(self, test_db):
        """Test random selection cache operations."""
        # Insert cache entry
        test_db.execute("""
            INSERT INTO random_cache (album_id, score, last_selected, selection_count)
            VALUES (?, ?, ?, ?)
        """, (123, 0.85, datetime.now().isoformat(), 5))
        test_db.commit()
        
        # Retrieve cache entry
        cursor = test_db.execute("SELECT * FROM random_cache WHERE album_id = ?", (123,))
        cache_entry = cursor.fetchone()
        
        assert cache_entry is not None
        assert cache_entry['album_id'] == 123
        assert cache_entry['score'] == 0.85
        assert cache_entry['selection_count'] == 5
    
    def test_database_constraints(self, test_db):
        """Test database constraints and data integrity."""
        # Test unique constraint on discogs_id
        test_db.execute("""
            INSERT INTO albums (discogs_id, title, artist)
            VALUES (999, 'Test Album', 'Test Artist')
        """)
        test_db.commit()
        
        # Try to insert duplicate discogs_id
        with pytest.raises(sqlite3.IntegrityError):
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist)
                VALUES (999, 'Another Album', 'Another Artist')
            """)
            test_db.commit()
    
    def test_database_indexes_performance(self, test_db):
        """Test that indexes improve query performance."""
        # Insert a larger dataset for performance testing
        albums = []
        for i in range(1000):
            albums.append((
                i,
                f'Album {i}',
                f'Artist {i % 100}',  # 100 different artists
                2000 + (i % 25),      # 25 different years
                ['Rock', 'Jazz', 'Electronic', 'Pop'][i % 4],  # 4 genres
                (i % 5) + 1           # Rating 1-5
            ))
        
        test_db.executemany("""
            INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """, albums)
        test_db.commit()
        
        # Test indexed queries (should be fast)
        import time
        
        # Query by discogs_id (should have index)
        start_time = time.time()
        cursor = test_db.execute("SELECT * FROM albums WHERE discogs_id = ?", (500,))
        result = cursor.fetchone()
        query_time = time.time() - start_time
        
        assert result is not None
        assert query_time < 0.1  # Should be very fast with index
        
        # Query by artist (if indexed)
        start_time = time.time()
        cursor = test_db.execute("SELECT * FROM albums WHERE artist = ?", ("Artist 50",))
        results = cursor.fetchall()
        query_time = time.time() - start_time
        
        assert len(results) > 0
        # Performance should be reasonable even without perfect indexing
        assert query_time < 0.5
    
    def test_transaction_rollback(self, test_db):
        """Test transaction rollback functionality."""
        initial_count = test_db.execute("SELECT COUNT(*) as count FROM albums").fetchone()['count']
        
        try:
            # Start transaction
            test_db.execute("BEGIN")
            
            # Insert valid data
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist)
                VALUES (1001, 'Test Album 1', 'Test Artist')
            """)
            
            # Insert invalid data (this should fail)
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist)
                VALUES (1001, 'Test Album 2', 'Test Artist')  -- Duplicate discogs_id
            """)
            
            test_db.commit()
            
        except sqlite3.IntegrityError:
            test_db.rollback()
        
        # Verify no data was inserted due to rollback
        final_count = test_db.execute("SELECT COUNT(*) as count FROM albums").fetchone()['count']
        assert final_count == initial_count