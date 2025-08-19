#!/usr/bin/env python3
"""
VinylVault Intelligent Random Record Selection Algorithm

This module implements a sophisticated random selection algorithm that:
1. Uses weighted selection based on user ratings, play counts, and recency
2. Maintains genre diversity to prevent clustering
3. Implements smart caching for instant response times
4. Learns from user behavior patterns
5. Optimizes for Raspberry Pi performance
"""

import json
import sqlite3
import logging
import random
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from pathlib import Path
import math

logger = logging.getLogger(__name__)


@dataclass
class SelectionMetrics:
    """Metrics for tracking algorithm performance."""
    total_selections: int = 0
    avg_response_time_ms: float = 0.0
    cache_hit_rate: float = 0.0
    genre_diversity_score: float = 0.0
    user_satisfaction_score: float = 0.0
    last_updated: datetime = None


@dataclass
class AlgorithmConfig:
    """Configuration parameters for the random selection algorithm."""
    # Weighting factors
    rating_weight: float = 2.0
    play_count_weight: float = 1.5
    recency_weight: float = 0.8
    genre_diversity_weight: float = 1.2
    
    # Cache settings
    cache_size: int = 20
    cache_refresh_threshold: int = 5
    max_history_size: int = 50
    
    # Selection constraints
    min_time_between_repeats_hours: int = 24
    genre_cooldown_selections: int = 3
    max_same_artist_streak: int = 2
    
    # Learning parameters
    feedback_learning_rate: float = 0.1
    seasonal_adjustment: bool = True
    time_based_preferences: bool = True
    
    # Performance settings
    max_computation_time_ms: int = 50
    precompute_weights: bool = True
    batch_cache_refresh: bool = True


class SelectionHistory:
    """Manages selection history and patterns."""
    
    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self.selections = deque(maxlen=max_size)
        self.genre_history = deque(maxlen=10)
        self.artist_history = deque(maxlen=5)
        
    def add_selection(self, album: Dict[str, Any]):
        """Add a selection to history."""
        selection = {
            'album_id': album['id'],
            'timestamp': datetime.now(),
            'genres': album.get('genres', []),
            'artist': album.get('artist', ''),
            'rating': album.get('rating', 0),
            'play_count': album.get('play_count', 0)
        }
        
        self.selections.append(selection)
        
        # Update genre and artist history
        if selection['genres']:
            self.genre_history.append(selection['genres'][0])
        self.artist_history.append(selection['artist'])
    
    def get_recent_albums(self, hours: int = 24) -> List[int]:
        """Get album IDs selected in the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [s['album_id'] for s in self.selections 
                if s['timestamp'] > cutoff]
    
    def get_recent_genres(self, count: int = 3) -> List[str]:
        """Get the last N selected genres."""
        return list(self.genre_history)[-count:]
    
    def get_recent_artists(self, count: int = 2) -> List[str]:
        """Get the last N selected artists."""
        return list(self.artist_history)[-count:]
    
    def clear(self):
        """Clear all history."""
        self.selections.clear()
        self.genre_history.clear()
        self.artist_history.clear()


class WeightCalculator:
    """Calculates selection weights based on various factors."""
    
    def __init__(self, config: AlgorithmConfig):
        self.config = config
        
    def calculate_rating_weight(self, rating: int) -> float:
        """Calculate weight based on user rating (1-5 stars)."""
        if rating is None or rating <= 0:
            return 0.5  # Neutral weight for unrated
        
        # Exponential scaling: 5-star gets much higher weight
        return math.pow(rating / 5.0, 2) * self.config.rating_weight + 0.1
    
    def calculate_play_count_weight(self, play_count: int, avg_play_count: float) -> float:
        """Calculate weight based on play frequency."""
        if play_count is None:
            play_count = 0
            
        if avg_play_count <= 0:
            return 1.0
            
        # Logarithmic scaling to prevent over-weighting frequently played albums
        normalized = play_count / avg_play_count
        return (math.log(normalized + 1) * self.config.play_count_weight) + 0.1
    
    def calculate_recency_weight(self, date_added: str, last_played: str = None) -> float:
        """Calculate weight based on how recently album was added/played."""
        try:
            added_date = datetime.fromisoformat(date_added.replace('Z', '+00:00'))
            now = datetime.now()
            
            # Newer additions get slightly higher weight
            days_since_added = (now - added_date).days
            recency_factor = math.exp(-days_since_added / 365.0)  # Decay over a year
            
            # Boost albums that haven't been played recently
            if last_played:
                last_played_date = datetime.fromisoformat(last_played.replace('Z', '+00:00'))
                days_since_played = (now - last_played_date).days
                play_recency_factor = math.log(days_since_played + 1) / 10.0
            else:
                play_recency_factor = 2.0  # Never played gets high boost
            
            return (recency_factor + play_recency_factor) * self.config.recency_weight
            
        except (ValueError, TypeError):
            return 1.0
    
    def calculate_genre_diversity_weight(self, genres: List[str], recent_genres: List[str]) -> float:
        """Calculate weight to promote genre diversity."""
        if not genres:
            return 1.0
            
        primary_genre = genres[0] if genres else None
        if not primary_genre:
            return 1.0
            
        # Reduce weight if genre was recently selected
        recent_count = recent_genres.count(primary_genre)
        if recent_count == 0:
            return 1.0 + self.config.genre_diversity_weight
        else:
            # Exponential penalty for repeated genres
            return max(0.1, 1.0 / (recent_count ** 2))
    
    def calculate_artist_diversity_weight(self, artist: str, recent_artists: List[str]) -> float:
        """Calculate weight to prevent same artist streaks."""
        if not artist:
            return 1.0
            
        recent_count = recent_artists.count(artist)
        if recent_count == 0:
            return 1.0
        else:
            # Strong penalty for artist repetition
            return max(0.05, 1.0 / (recent_count ** 3))
    
    def apply_seasonal_adjustment(self, genres: List[str], weight: float) -> float:
        """Apply seasonal adjustments to weights."""
        if not self.config.seasonal_adjustment or not genres:
            return weight
            
        current_month = datetime.now().month
        primary_genre = genres[0].lower() if genres else ""
        
        # Simple seasonal preferences
        seasonal_boosts = {
            'christmas': [12, 1],  # December, January
            'holiday': [12, 1],
            'jazz': [10, 11, 12],  # Fall/Winter
            'classical': [10, 11, 12, 1, 2],  # Classical in colder months
            'electronic': [6, 7, 8],  # Summer
            'reggae': [6, 7, 8],
            'folk': [9, 10, 11],  # Fall
            'acoustic': [9, 10, 11]
        }
        
        for genre_key, months in seasonal_boosts.items():
            if genre_key in primary_genre and current_month in months:
                return weight * 1.3
                
        return weight
    
    def apply_time_based_adjustment(self, genres: List[str], weight: float) -> float:
        """Apply time-of-day based adjustments."""
        if not self.config.time_based_preferences or not genres:
            return weight
            
        current_hour = datetime.now().hour
        primary_genre = genres[0].lower() if genres else ""
        
        # Time-based preferences
        if 6 <= current_hour <= 10:  # Morning
            if any(g in primary_genre for g in ['classical', 'acoustic', 'folk', 'jazz']):
                return weight * 1.2
        elif 18 <= current_hour <= 22:  # Evening
            if any(g in primary_genre for g in ['electronic', 'rock', 'pop']):
                return weight * 1.2
        elif 22 <= current_hour or current_hour <= 6:  # Night
            if any(g in primary_genre for g in ['ambient', 'classical', 'jazz']):
                return weight * 1.3
                
        return weight


class RandomAlgorithm:
    """Intelligent random record selection algorithm."""
    
    def __init__(self, db_path: str, config: AlgorithmConfig = None):
        self.db_path = db_path
        self.config = config or AlgorithmConfig()
        self.weight_calculator = WeightCalculator(self.config)
        self.history = SelectionHistory(self.config.max_history_size)
        self.metrics = SelectionMetrics()
        self.cache_lock = threading.Lock()
        self.last_cache_refresh = datetime.now()
        
        # Initialize algorithm state
        self._initialize_database_extensions()
        self._load_selection_history()
        self._refresh_selection_cache()
    
    def _initialize_database_extensions(self):
        """Initialize additional database tables for algorithm intelligence."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Selection history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS selection_history (
                    id INTEGER PRIMARY KEY,
                    album_id INTEGER,
                    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_feedback INTEGER,  -- -1 (dislike), 0 (neutral), 1 (like)
                    session_id TEXT,
                    algorithm_version TEXT DEFAULT '1.0',
                    weight_factors TEXT,  -- JSON of weights used
                    FOREIGN KEY (album_id) REFERENCES albums (id)
                )
            """)
            
            # Algorithm metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS algorithm_metrics (
                    id INTEGER PRIMARY KEY,
                    metric_date DATE DEFAULT CURRENT_DATE,
                    total_selections INTEGER DEFAULT 0,
                    avg_response_time_ms REAL DEFAULT 0.0,
                    cache_hit_rate REAL DEFAULT 0.0,
                    genre_diversity_score REAL DEFAULT 0.0,
                    user_satisfaction_score REAL DEFAULT 0.0,
                    config_snapshot TEXT  -- JSON of config used
                )
            """)
            
            # Enhanced random cache with intelligence
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intelligent_cache (
                    id INTEGER PRIMARY KEY,
                    album_id INTEGER,
                    base_weight REAL DEFAULT 1.0,
                    rating_weight REAL DEFAULT 1.0,
                    play_count_weight REAL DEFAULT 1.0,
                    recency_weight REAL DEFAULT 1.0,
                    diversity_weight REAL DEFAULT 1.0,
                    final_weight REAL DEFAULT 1.0,
                    last_computed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    times_served INTEGER DEFAULT 0,
                    last_served TIMESTAMP,
                    FOREIGN KEY (album_id) REFERENCES albums (id)
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_selection_history_album ON selection_history (album_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_selection_history_time ON selection_history (selected_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intelligent_cache_weight ON intelligent_cache (final_weight)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intelligent_cache_served ON intelligent_cache (last_served)")
            
            conn.commit()
    
    def _load_selection_history(self):
        """Load recent selection history from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Load recent selections
                cursor = conn.execute("""
                    SELECT sh.*, a.artist, a.genres, a.rating, a.play_count
                    FROM selection_history sh
                    JOIN albums a ON sh.album_id = a.id
                    WHERE sh.selected_at > datetime('now', '-7 days')
                    ORDER BY sh.selected_at DESC
                    LIMIT ?
                """, (self.config.max_history_size,))
                
                for row in cursor.fetchall():
                    album_data = {
                        'id': row['album_id'],
                        'artist': row['artist'],
                        'genres': json.loads(row['genres'] or '[]'),
                        'rating': row['rating'],
                        'play_count': row['play_count']
                    }
                    self.history.add_selection(album_data)
                    
        except Exception as e:
            logger.error(f"Error loading selection history: {e}")
    
    def _refresh_selection_cache(self):
        """Refresh the intelligent selection cache with computed weights."""
        start_time = time.time()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Get all albums with their current stats
                cursor = conn.execute("""
                    SELECT id, title, artist, year, genres, styles, rating,
                           play_count, date_added, last_played
                    FROM albums
                    ORDER BY id
                """)
                albums = cursor.fetchall()
                
                if not albums:
                    logger.warning("No albums found for cache refresh")
                    return
                
                # Calculate average play count for normalization
                play_counts = [a['play_count'] or 0 for a in albums]
                avg_play_count = sum(play_counts) / len(play_counts) if play_counts else 1.0
                
                # Get recent selections for diversity calculation
                recent_genres = self.history.get_recent_genres(self.config.genre_cooldown_selections)
                recent_artists = self.history.get_recent_artists(self.config.max_same_artist_streak)
                recent_albums = self.history.get_recent_albums(self.config.min_time_between_repeats_hours)
                
                # Calculate weights for each album
                cache_entries = []
                for album in albums:
                    try:
                        genres = json.loads(album['genres'] or '[]')
                        
                        # Skip recently selected albums
                        if album['id'] in recent_albums:
                            continue
                        
                        # Calculate individual weight components
                        rating_weight = self.weight_calculator.calculate_rating_weight(album['rating'])
                        play_count_weight = self.weight_calculator.calculate_play_count_weight(
                            album['play_count'], avg_play_count
                        )
                        recency_weight = self.weight_calculator.calculate_recency_weight(
                            album['date_added'], album['last_played']
                        )
                        diversity_weight = self.weight_calculator.calculate_genre_diversity_weight(
                            genres, recent_genres
                        )
                        artist_weight = self.weight_calculator.calculate_artist_diversity_weight(
                            album['artist'], recent_artists
                        )
                        
                        # Combine weights
                        base_weight = rating_weight * play_count_weight * recency_weight
                        final_weight = base_weight * diversity_weight * artist_weight
                        
                        # Apply seasonal and time-based adjustments
                        final_weight = self.weight_calculator.apply_seasonal_adjustment(genres, final_weight)
                        final_weight = self.weight_calculator.apply_time_based_adjustment(genres, final_weight)
                        
                        # Ensure minimum weight
                        final_weight = max(0.01, final_weight)
                        
                        cache_entries.append((
                            album['id'], 1.0, rating_weight, play_count_weight,
                            recency_weight, diversity_weight, final_weight,
                            datetime.now().isoformat()
                        ))
                        
                    except Exception as e:
                        logger.error(f"Error calculating weights for album {album['id']}: {e}")
                        continue
                
                # Clear old cache and insert new entries
                conn.execute("DELETE FROM intelligent_cache")
                
                if cache_entries:
                    conn.executemany("""
                        INSERT INTO intelligent_cache 
                        (album_id, base_weight, rating_weight, play_count_weight,
                         recency_weight, diversity_weight, final_weight, last_computed)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, cache_entries)
                
                conn.commit()
                
                elapsed_ms = (time.time() - start_time) * 1000
                logger.info(f"Cache refreshed with {len(cache_entries)} entries in {elapsed_ms:.1f}ms")
                
                self.last_cache_refresh = datetime.now()
                
        except Exception as e:
            logger.error(f"Error refreshing selection cache: {e}")
    
    def select_random_album(self, session_id: str = None) -> Optional[Dict[str, Any]]:
        """Select a random album using intelligent weighting."""
        start_time = time.time()
        
        try:
            with self.cache_lock:
                # Check if cache needs refresh
                cache_age = datetime.now() - self.last_cache_refresh
                if cache_age.total_seconds() > 3600:  # Refresh every hour
                    self._refresh_selection_cache()
                
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    
                    # Get weighted selection from cache
                    cursor = conn.execute("""
                        SELECT ic.*, a.title, a.artist, a.year, a.cover_url, a.genres, a.styles
                        FROM intelligent_cache ic
                        JOIN albums a ON ic.album_id = a.id
                        WHERE ic.final_weight > 0
                        ORDER BY RANDOM() * ic.final_weight DESC
                        LIMIT 1
                    """)
                    
                    result = cursor.fetchone()
                    
                    if not result:
                        # Fallback to simple random selection
                        cursor = conn.execute("""
                            SELECT * FROM albums 
                            ORDER BY RANDOM() 
                            LIMIT 1
                        """)
                        result = cursor.fetchone()
                        
                        if not result:
                            return None
                    
                    # Convert to dictionary
                    album = dict(result)
                    
                    # Parse JSON fields
                    try:
                        album['genres'] = json.loads(album.get('genres', '[]') or '[]')
                        album['styles'] = json.loads(album.get('styles', '[]') or '[]')
                    except json.JSONDecodeError:
                        album['genres'] = []
                        album['styles'] = []
                    
                    # Record selection in history
                    self._record_selection(album, session_id, conn)
                    
                    # Update cache statistics
                    if 'final_weight' in album:
                        conn.execute("""
                            UPDATE intelligent_cache 
                            SET times_served = times_served + 1,
                                last_served = ?
                            WHERE album_id = ?
                        """, (datetime.now().isoformat(), album['id']))
                        conn.commit()
                    
                    # Update history
                    self.history.add_selection(album)
                    
                    # Update metrics
                    elapsed_ms = (time.time() - start_time) * 1000
                    self._update_metrics(elapsed_ms, True)
                    
                    return album
                    
        except Exception as e:
            logger.error(f"Error in intelligent album selection: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            self._update_metrics(elapsed_ms, False)
            return None
    
    def _record_selection(self, album: Dict[str, Any], session_id: str, conn):
        """Record the selection in history."""
        try:
            weight_factors = {
                'rating_weight': album.get('rating_weight', 1.0),
                'play_count_weight': album.get('play_count_weight', 1.0),
                'recency_weight': album.get('recency_weight', 1.0),
                'diversity_weight': album.get('diversity_weight', 1.0),
                'final_weight': album.get('final_weight', 1.0)
            }
            
            conn.execute("""
                INSERT INTO selection_history 
                (album_id, session_id, algorithm_version, weight_factors)
                VALUES (?, ?, ?, ?)
            """, (
                album['id'], 
                session_id or 'anonymous',
                '1.0',
                json.dumps(weight_factors)
            ))
            
        except Exception as e:
            logger.error(f"Error recording selection: {e}")
    
    def _update_metrics(self, response_time_ms: float, success: bool):
        """Update algorithm performance metrics."""
        try:
            self.metrics.total_selections += 1
            
            # Update rolling average response time
            alpha = 0.1  # Smoothing factor
            self.metrics.avg_response_time_ms = (
                alpha * response_time_ms + 
                (1 - alpha) * self.metrics.avg_response_time_ms
            )
            
            # Update cache hit rate
            if success:
                self.metrics.cache_hit_rate = (
                    alpha * 1.0 + (1 - alpha) * self.metrics.cache_hit_rate
                )
            else:
                self.metrics.cache_hit_rate = (
                    alpha * 0.0 + (1 - alpha) * self.metrics.cache_hit_rate
                )
            
            self.metrics.last_updated = datetime.now()
            
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
    
    def record_user_feedback(self, album_id: int, feedback: int, session_id: str = None):
        """Record user feedback for machine learning (-1: dislike, 0: neutral, 1: like)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Update the most recent selection of this album
                conn.execute("""
                    UPDATE selection_history 
                    SET user_feedback = ?
                    WHERE album_id = ? AND session_id = ? AND user_feedback IS NULL
                    ORDER BY selected_at DESC
                    LIMIT 1
                """, (feedback, album_id, session_id or 'anonymous'))
                
                conn.commit()
                
                # Update user satisfaction metric
                if feedback != 0:
                    alpha = self.config.feedback_learning_rate
                    satisfaction_update = 1.0 if feedback > 0 else 0.0
                    self.metrics.user_satisfaction_score = (
                        alpha * satisfaction_update + 
                        (1 - alpha) * self.metrics.user_satisfaction_score
                    )
                
        except Exception as e:
            logger.error(f"Error recording user feedback: {e}")
    
    def get_algorithm_stats(self) -> Dict[str, Any]:
        """Get comprehensive algorithm statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Selection statistics
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_selections,
                           COUNT(CASE WHEN user_feedback = 1 THEN 1 END) as positive_feedback,
                           COUNT(CASE WHEN user_feedback = -1 THEN 1 END) as negative_feedback,
                           AVG(CASE WHEN user_feedback IS NOT NULL THEN user_feedback END) as avg_feedback
                    FROM selection_history
                    WHERE selected_at > datetime('now', '-30 days')
                """)
                selection_stats = dict(cursor.fetchone())
                
                # Genre diversity statistics
                cursor = conn.execute("""
                    SELECT COUNT(DISTINCT json_extract(a.genres, '$[0]')) as unique_genres_selected
                    FROM selection_history sh
                    JOIN albums a ON sh.album_id = a.id
                    WHERE sh.selected_at > datetime('now', '-30 days')
                      AND a.genres IS NOT NULL
                      AND a.genres != '[]'
                """)
                genre_stats = dict(cursor.fetchone())
                
                # Cache statistics
                cursor = conn.execute("""
                    SELECT COUNT(*) as cached_albums,
                           AVG(final_weight) as avg_weight,
                           MAX(final_weight) as max_weight,
                           MIN(final_weight) as min_weight
                    FROM intelligent_cache
                """)
                cache_stats = dict(cursor.fetchone())
                
                return {
                    'metrics': asdict(self.metrics),
                    'selection_stats': selection_stats,
                    'genre_stats': genre_stats,
                    'cache_stats': cache_stats,
                    'config': asdict(self.config),
                    'history_size': len(self.history.selections)
                }
                
        except Exception as e:
            logger.error(f"Error getting algorithm stats: {e}")
            return {'error': str(e)}
    
    def optimize_config(self) -> AlgorithmConfig:
        """Optimize algorithm configuration based on user feedback."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Get feedback data for analysis
                cursor = conn.execute("""
                    SELECT sh.user_feedback, sh.weight_factors, a.rating, a.play_count, a.genres
                    FROM selection_history sh
                    JOIN albums a ON sh.album_id = a.id
                    WHERE sh.user_feedback IS NOT NULL
                      AND sh.selected_at > datetime('now', '-30 days')
                """)
                
                feedback_data = cursor.fetchall()
                
                if len(feedback_data) < 10:  # Need minimum data for optimization
                    return self.config
                
                # Analyze patterns in positive vs negative feedback
                positive_weights = []
                negative_weights = []
                
                for row in feedback_data:
                    try:
                        weights = json.loads(row['weight_factors'])
                        if row['user_feedback'] > 0:
                            positive_weights.append(weights)
                        elif row['user_feedback'] < 0:
                            negative_weights.append(weights)
                    except (json.JSONDecodeError, TypeError):
                        continue
                
                # Simple optimization: adjust weights based on feedback patterns
                new_config = AlgorithmConfig(
                    rating_weight=self.config.rating_weight,
                    play_count_weight=self.config.play_count_weight,
                    recency_weight=self.config.recency_weight,
                    genre_diversity_weight=self.config.genre_diversity_weight
                )
                
                # Increase weights that correlate with positive feedback
                if positive_weights:
                    avg_positive_rating = sum(w.get('rating_weight', 1.0) for w in positive_weights) / len(positive_weights)
                    if avg_positive_rating > self.config.rating_weight:
                        new_config.rating_weight = min(3.0, avg_positive_rating * 1.1)
                
                logger.info("Algorithm configuration optimized based on user feedback")
                return new_config
                
        except Exception as e:
            logger.error(f"Error optimizing config: {e}")
            return self.config
    
    def trigger_cache_refresh(self):
        """Manually trigger cache refresh (called after collection changes)."""
        with self.cache_lock:
            self._refresh_selection_cache()
    
    def clear_history(self):
        """Clear selection history (for testing or reset)."""
        self.history.clear()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM selection_history")
                conn.execute("DELETE FROM algorithm_metrics")
                conn.commit()
        except Exception as e:
            logger.error(f"Error clearing history: {e}")


# Global algorithm instance
_algorithm_instance = None
_algorithm_lock = threading.Lock()


def get_algorithm_instance(db_path: str, config: AlgorithmConfig = None) -> RandomAlgorithm:
    """Get or create the global algorithm instance."""
    global _algorithm_instance
    
    with _algorithm_lock:
        if _algorithm_instance is None:
            _algorithm_instance = RandomAlgorithm(db_path, config)
        return _algorithm_instance


def initialize_random_algorithm(db_path: str, config: AlgorithmConfig = None) -> bool:
    """Initialize the random algorithm for the application."""
    try:
        algorithm = get_algorithm_instance(db_path, config)
        logger.info("Random algorithm initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing random algorithm: {e}")
        return False


def get_random_album(db_path: str, session_id: str = None) -> Optional[Dict[str, Any]]:
    """Get a random album using the intelligent algorithm."""
    try:
        algorithm = get_algorithm_instance(db_path)
        return algorithm.select_random_album(session_id)
    except Exception as e:
        logger.error(f"Error getting random album: {e}")
        return None


def record_album_feedback(db_path: str, album_id: int, feedback: int, session_id: str = None):
    """Record user feedback for an album selection."""
    try:
        algorithm = get_algorithm_instance(db_path)
        algorithm.record_user_feedback(album_id, feedback, session_id)
    except Exception as e:
        logger.error(f"Error recording album feedback: {e}")


def get_algorithm_statistics(db_path: str) -> Dict[str, Any]:
    """Get comprehensive algorithm statistics."""
    try:
        algorithm = get_algorithm_instance(db_path)
        return algorithm.get_algorithm_stats()
    except Exception as e:
        logger.error(f"Error getting algorithm statistics: {e}")
        return {'error': str(e)}


def refresh_algorithm_cache(db_path: str):
    """Refresh the algorithm cache (call after collection changes)."""
    try:
        algorithm = get_algorithm_instance(db_path)
        algorithm.trigger_cache_refresh()
    except Exception as e:
        logger.error(f"Error refreshing algorithm cache: {e}")