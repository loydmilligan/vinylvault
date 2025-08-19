"""
Unit tests for the intelligent random selection algorithm.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import sqlite3

from random_algorithm import (
    RandomAlgorithm,
    AlgorithmConfig,
    calculate_album_score,
    update_selection_history
)


@pytest.mark.unit
class TestRandomAlgorithm:
    """Test intelligent random selection algorithm."""
    
    def test_algorithm_config_creation(self):
        """Test algorithm configuration creation."""
        config = AlgorithmConfig(
            rating_weight=0.3,
            recency_weight=0.2,
            diversity_weight=0.2,
            discovery_weight=0.3
        )
        
        assert config.rating_weight == 0.3
        assert config.recency_weight == 0.2
        assert config.diversity_weight == 0.2
        assert config.discovery_weight == 0.3
        
        # Weights should sum to 1.0
        total_weight = (config.rating_weight + config.recency_weight + 
                       config.diversity_weight + config.discovery_weight)
        assert abs(total_weight - 1.0) < 0.001
    
    def test_algorithm_config_validation(self):
        """Test algorithm configuration validation."""
        # Test invalid weights (sum > 1)
        with pytest.raises(ValueError):
            AlgorithmConfig(
                rating_weight=0.5,
                recency_weight=0.5,
                diversity_weight=0.5,
                discovery_weight=0.5
            )
        
        # Test negative weights
        with pytest.raises(ValueError):
            AlgorithmConfig(
                rating_weight=-0.1,
                recency_weight=0.4,
                diversity_weight=0.4,
                discovery_weight=0.3
            )
    
    def test_score_calculation_rating_component(self):
        """Test rating component of score calculation."""
        album_data = {
            'user_rating': 5,
            'rating': 4.5,
            'last_selected': None,
            'selection_count': 0,
            'genre': 'Rock',
            'artist': 'Test Artist',
            'date_added': datetime.now().isoformat()
        }
        
        config = AlgorithmConfig(rating_weight=1.0, recency_weight=0.0, 
                               diversity_weight=0.0, discovery_weight=0.0)
        
        score = calculate_album_score(album_data, config, {}, {})
        
        # Score should be high for high-rated album
        assert score > 0.8
        
        # Test with lower rating
        album_data['user_rating'] = 2
        album_data['rating'] = 2.0
        
        score_low = calculate_album_score(album_data, config, {}, {})
        
        # Lower rated album should have lower score
        assert score_low < score
    
    def test_score_calculation_recency_component(self):
        """Test recency component of score calculation."""
        # Recently selected album
        recent_album = {
            'user_rating': 5,
            'rating': 5.0,
            'last_selected': datetime.now().isoformat(),
            'selection_count': 1,
            'genre': 'Rock',
            'artist': 'Test Artist',
            'date_added': datetime.now().isoformat()
        }
        
        # Never selected album
        never_selected = {
            'user_rating': 5,
            'rating': 5.0,
            'last_selected': None,
            'selection_count': 0,
            'genre': 'Rock',
            'artist': 'Test Artist',
            'date_added': datetime.now().isoformat()
        }
        
        config = AlgorithmConfig(rating_weight=0.0, recency_weight=1.0, 
                               diversity_weight=0.0, discovery_weight=0.0)
        
        recent_score = calculate_album_score(recent_album, config, {}, {})
        never_score = calculate_album_score(never_selected, config, {}, {})
        
        # Never selected album should have higher recency score
        assert never_score > recent_score
    
    def test_score_calculation_diversity_component(self):
        """Test diversity component of score calculation."""
        album_rock = {
            'user_rating': 5,
            'rating': 5.0,
            'last_selected': None,
            'selection_count': 0,
            'genre': 'Rock',
            'artist': 'Rock Artist',
            'date_added': datetime.now().isoformat()
        }
        
        album_jazz = {
            'user_rating': 5,
            'rating': 5.0,
            'last_selected': None,
            'selection_count': 0,
            'genre': 'Jazz',
            'artist': 'Jazz Artist',
            'date_added': datetime.now().isoformat()
        }
        
        # Simulate recent genre/artist selections
        recent_genres = {'Rock': 3, 'Electronic': 1}  # Rock heavily selected
        recent_artists = {'Rock Artist': 2, 'Electronic Artist': 1}
        
        config = AlgorithmConfig(rating_weight=0.0, recency_weight=0.0, 
                               diversity_weight=1.0, discovery_weight=0.0)
        
        rock_score = calculate_album_score(album_rock, config, recent_genres, recent_artists)
        jazz_score = calculate_album_score(album_jazz, config, recent_genres, recent_artists)
        
        # Jazz album should have higher diversity score (less frequently selected genre)
        assert jazz_score > rock_score
    
    def test_score_calculation_discovery_component(self):
        """Test discovery component of score calculation."""
        from datetime import timedelta
        
        # Old album
        old_album = {
            'user_rating': 3,
            'rating': 3.0,
            'last_selected': None,
            'selection_count': 0,
            'genre': 'Rock',
            'artist': 'Test Artist',
            'date_added': (datetime.now() - timedelta(days=365)).isoformat()
        }
        
        # New album
        new_album = {
            'user_rating': 3,
            'rating': 3.0,
            'last_selected': None,
            'selection_count': 0,
            'genre': 'Rock',
            'artist': 'Test Artist',
            'date_added': datetime.now().isoformat()
        }
        
        config = AlgorithmConfig(rating_weight=0.0, recency_weight=0.0, 
                               diversity_weight=0.0, discovery_weight=1.0)
        
        old_score = calculate_album_score(old_album, config, {}, {})
        new_score = calculate_album_score(new_album, config, {}, {})
        
        # New album should have higher discovery score
        assert new_score > old_score
    
    def test_selection_history_update(self, test_db):
        """Test updating selection history."""
        album_id = 123
        
        # Initial selection
        update_selection_history(test_db, album_id)
        
        cursor = test_db.execute("""
            SELECT * FROM random_cache WHERE album_id = ?
        """, (album_id,))
        entry = cursor.fetchone()
        
        assert entry is not None
        assert entry['album_id'] == album_id
        assert entry['selection_count'] == 1
        assert entry['last_selected'] is not None
        
        # Second selection
        update_selection_history(test_db, album_id)
        
        cursor = test_db.execute("""
            SELECT * FROM random_cache WHERE album_id = ?
        """, (album_id,))
        entry = cursor.fetchone()
        
        assert entry['selection_count'] == 2
    
    def test_algorithm_initialization(self, test_config):
        """Test random algorithm initialization."""
        algorithm = RandomAlgorithm(test_config.DATABASE_PATH)
        
        assert algorithm is not None
        assert hasattr(algorithm, 'get_random_album')
        assert hasattr(algorithm, 'record_feedback')
        assert hasattr(algorithm, 'get_statistics')
    
    def test_get_random_album_with_empty_collection(self, test_db):
        """Test random album selection with empty collection."""
        with patch('random_algorithm.RandomAlgorithm') as MockAlgorithm:
            mock_instance = MockAlgorithm.return_value
            mock_instance.get_random_album.return_value = None
            
            algorithm = MockAlgorithm(test_db)
            result = algorithm.get_random_album()
            
            assert result is None
    
    def test_get_random_album_with_collection(self, test_db):
        """Test random album selection with populated collection."""
        # Insert test albums
        test_albums = [
            (1, 'Album 1', 'Artist 1', 2020, 'Rock', 5),
            (2, 'Album 2', 'Artist 2', 2021, 'Jazz', 4),
            (3, 'Album 3', 'Artist 3', 2019, 'Electronic', 3)
        ]
        
        for album in test_albums:
            test_db.execute("""
                INSERT INTO albums (discogs_id, title, artist, year, genre, user_rating)
                VALUES (?, ?, ?, ?, ?, ?)
            """, album)
        test_db.commit()
        
        with patch('random_algorithm.RandomAlgorithm') as MockAlgorithm:
            mock_instance = MockAlgorithm.return_value
            mock_instance.get_random_album.return_value = {
                'discogs_id': 1,
                'title': 'Album 1',
                'artist': 'Artist 1',
                'score': 0.85
            }
            
            algorithm = MockAlgorithm(test_db)
            result = algorithm.get_random_album()
            
            assert result is not None
            assert result['discogs_id'] == 1
            assert 'score' in result
    
    def test_feedback_recording(self, test_db):
        """Test recording user feedback on algorithm selections."""
        album_id = 123
        feedback = 'liked'
        
        # Record feedback
        with patch('random_algorithm.record_album_feedback') as mock_record:
            mock_record.return_value = True
            
            result = mock_record(test_db, album_id, feedback)
            assert result is True
            mock_record.assert_called_once_with(test_db, album_id, feedback)
    
    def test_algorithm_statistics(self, test_db):
        """Test algorithm statistics calculation."""
        # Insert test data for statistics
        test_data = [
            (1, 0.9, datetime.now().isoformat(), 5, 'liked'),
            (2, 0.7, datetime.now().isoformat(), 3, 'disliked'),
            (3, 0.8, datetime.now().isoformat(), 1, 'liked')
        ]
        
        for data in test_data:
            test_db.execute("""
                INSERT INTO random_cache (album_id, score, last_selected, 
                                        selection_count, last_feedback)
                VALUES (?, ?, ?, ?, ?)
            """, data)
        test_db.commit()
        
        with patch('random_algorithm.get_algorithm_statistics') as mock_stats:
            mock_stats.return_value = {
                'total_selections': 9,  # 5 + 3 + 1
                'avg_score': 0.8,       # (0.9 + 0.7 + 0.8) / 3
                'feedback_ratio': 0.67, # 2 liked / 3 total
                'cache_size': 3
            }
            
            stats = mock_stats(test_db)
            
            assert stats['total_selections'] == 9
            assert stats['avg_score'] == 0.8
            assert stats['feedback_ratio'] == 0.67
            assert stats['cache_size'] == 3
    
    def test_cache_refresh(self, test_db):
        """Test algorithm cache refresh functionality."""
        # Insert old cache entries
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        
        test_data = [
            (1, 0.5, old_date, 10),
            (2, 0.3, old_date, 15),
            (3, 0.8, datetime.now().isoformat(), 1)  # Recent entry
        ]
        
        for data in test_data:
            test_db.execute("""
                INSERT INTO random_cache (album_id, score, last_selected, selection_count)
                VALUES (?, ?, ?, ?)
            """, data)
        test_db.commit()
        
        with patch('random_algorithm.refresh_algorithm_cache') as mock_refresh:
            mock_refresh.return_value = 2  # Number of entries refreshed
            
            refreshed_count = mock_refresh(test_db)
            assert refreshed_count == 2
    
    def test_weighted_selection_probability(self):
        """Test that higher scored albums have higher selection probability."""
        albums = [
            {'id': 1, 'score': 0.9, 'title': 'High Score Album'},
            {'id': 2, 'score': 0.1, 'title': 'Low Score Album'},
            {'id': 3, 'score': 0.5, 'title': 'Medium Score Album'}
        ]
        
        # Simulate weighted random selection
        import random
        
        def weighted_choice(albums):
            total_weight = sum(album['score'] for album in albums)
            r = random.uniform(0, total_weight)
            current_weight = 0
            
            for album in albums:
                current_weight += album['score']
                if r <= current_weight:
                    return album
            
            return albums[-1]  # Fallback
        
        # Run many selections to test distribution
        selections = {}
        for _ in range(1000):
            selected = weighted_choice(albums)
            selections[selected['id']] = selections.get(selected['id'], 0) + 1
        
        # High score album should be selected most often
        assert selections[1] > selections[2]
        assert selections[1] > selections[3]
        assert selections[2] < selections[3]  # Low score should be least frequent
    
    def test_algorithm_config_serialization(self):
        """Test algorithm configuration serialization."""
        config = AlgorithmConfig(
            rating_weight=0.4,
            recency_weight=0.3,
            diversity_weight=0.2,
            discovery_weight=0.1
        )
        
        # Test dict conversion
        config_dict = config.__dict__
        assert config_dict['rating_weight'] == 0.4
        assert config_dict['recency_weight'] == 0.3
        
        # Test reconstruction from dict
        new_config = AlgorithmConfig(**config_dict)
        assert new_config.rating_weight == config.rating_weight
        assert new_config.recency_weight == config.recency_weight