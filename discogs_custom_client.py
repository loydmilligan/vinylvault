#!/usr/bin/env python3
"""
VinylVault Discogs API Integration Module

This module provides a comprehensive interface to the Discogs API with:
- Secure token management and encryption
- Rate-limited collection fetching with pagination
- Robust error handling and retry logic
- Data parsing and normalization for database storage
- Background sync capabilities
- Offline mode support
- Session management and connection pooling
"""

import json
import time
import logging
import sqlite3
import requests
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Iterator
from functools import wraps, lru_cache
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import discogs_client
from cryptography.fernet import Fernet
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from config import Config

# Configure module-specific logging
logger = logging.getLogger(__name__)

class DiscogsAPIError(Exception):
    """Custom exception for Discogs API errors."""
    pass

class DiscogsRateLimitError(DiscogsAPIError):
    """Exception for rate limit exceeded."""
    pass

class DiscogsAuthenticationError(DiscogsAPIError):
    """Exception for authentication failures."""
    pass

class DiscogsConnectionError(DiscogsAPIError):
    """Exception for connection issues."""
    pass

class DiscogsRateLimiter:
    """
    Rate limiter to respect Discogs API limits (60 requests per minute).
    Uses token bucket algorithm for smooth request distribution.
    """
    
    def __init__(self, max_requests: int = 50, window: int = 60):
        """Initialize rate limiter with conservative defaults."""
        self.max_requests = max_requests  # Conservative limit (Discogs allows 60)
        self.window = window
        self.requests = []
        self.lock = threading.Lock()
        
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        with self.lock:
            now = time.time()
            
            # Remove old requests outside the window
            self.requests = [req_time for req_time in self.requests if now - req_time < self.window]
            
            # Check if we need to wait
            if len(self.requests) >= self.max_requests:
                oldest_request = min(self.requests)
                wait_time = self.window - (now - oldest_request) + 0.1  # Small buffer
                if wait_time > 0:
                    logger.info(f"Rate limit approaching, waiting {wait_time:.1f} seconds")
                    time.sleep(wait_time)
                    # Clean up again after waiting
                    now = time.time()
                    self.requests = [req_time for req_time in self.requests if now - req_time < self.window]
            
            # Record this request
            self.requests.append(now)

class DiscogsSession:
    """
    Enhanced session management with connection pooling and retries.
    """
    
    def __init__(self):
        self.session = requests.Session()
        
        # Configure retries with exponential backoff
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=2,
            respect_retry_after_header=True
        )
        
        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=5,
            pool_maxsize=10,
            pool_block=True
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set reasonable timeouts
        self.session.timeout = (10, 30)  # (connect, read)
        
    def get(self, *args, **kwargs):
        """Enhanced GET with error handling."""
        try:
            response = self.session.get(*args, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise DiscogsConnectionError("Request timeout")
        except requests.exceptions.ConnectionError:
            raise DiscogsConnectionError("Connection error")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise DiscogsRateLimitError("Rate limit exceeded")
            elif e.response.status_code in [401, 403]:
                raise DiscogsAuthenticationError("Authentication failed")
            else:
                raise DiscogsAPIError(f"HTTP error: {e.response.status_code}")

class DiscogsCollectionSyncer:
    """
    Handles collection synchronization with progress tracking and error recovery.
    """
    
    def __init__(self, discogs_client: 'DiscogsClient'):
        self.client = discogs_client
        self.is_syncing = False
        self.sync_progress = {
            'total_items': 0,
            'processed_items': 0,
            'current_page': 0,
            'total_pages': 0,
            'status': 'idle',
            'start_time': None,
            'estimated_completion': None,
            'errors': []
        }
        self.sync_lock = threading.Lock()
        
    def start_background_sync(self, force_full: bool = False) -> bool:
        """Start background synchronization in a separate thread."""
        with self.sync_lock:
            if self.is_syncing:
                logger.warning("Sync already in progress")
                return False
            
            self.is_syncing = True
            self.sync_progress.update({
                'status': 'starting',
                'start_time': datetime.now(),
                'errors': []
            })
        
        # Start sync in background thread
        sync_thread = threading.Thread(
            target=self._sync_collection_worker,
            args=(force_full,),
            daemon=True
        )
        sync_thread.start()
        return True
    
    def _sync_collection_worker(self, force_full: bool):
        """Worker thread for collection synchronization."""
        try:
            self.sync_progress['status'] = 'fetching_collection_info'
            
            # Get collection info to determine total items
            collection_info = self.client._get_collection_info()
            total_items = collection_info.get('count', 0)
            
            self.sync_progress.update({
                'total_items': total_items,
                'total_pages': (total_items + 99) // 100,  # 100 items per page
                'status': 'syncing'
            })
            
            logger.info(f"Starting sync of {total_items} items")
            
            # Sync collection with progress tracking
            synced_count = 0
            for page_num, page_items in enumerate(self.client._fetch_collection_pages(), 1):
                if not self.is_syncing:  # Check for cancellation
                    break
                
                self.sync_progress['current_page'] = page_num
                
                # Process items in this page
                for item in page_items:
                    try:
                        self.client._process_collection_item(item)
                        synced_count += 1
                        self.sync_progress['processed_items'] = synced_count
                        
                        # Update estimated completion
                        if synced_count > 0:
                            elapsed = (datetime.now() - self.sync_progress['start_time']).total_seconds()
                            rate = synced_count / elapsed  # items per second
                            remaining_items = total_items - synced_count
                            eta_seconds = remaining_items / rate if rate > 0 else 0
                            self.sync_progress['estimated_completion'] = (
                                datetime.now() + timedelta(seconds=eta_seconds)
                            )
                        
                    except Exception as e:
                        error_msg = f"Error processing item {item.get('id', 'unknown')}: {str(e)}"
                        logger.error(error_msg)
                        self.sync_progress['errors'].append(error_msg)
                        
                        # Stop if too many errors
                        if len(self.sync_progress['errors']) > 10:
                            raise DiscogsAPIError("Too many errors during sync")
            
            # Update sync status
            self.client._update_sync_log(synced_count, 'completed')
            self.sync_progress['status'] = 'completed'
            logger.info(f"Sync completed successfully. Processed {synced_count} items.")
            
        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            logger.error(error_msg)
            self.sync_progress['status'] = 'failed'
            self.sync_progress['errors'].append(error_msg)
            self.client._update_sync_log(self.sync_progress['processed_items'], 'failed')
            
        finally:
            with self.sync_lock:
                self.is_syncing = False
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status and progress."""
        with self.sync_lock:
            status = self.sync_progress.copy()
            
            # Convert datetime objects to ISO strings for JSON serialization
            if status.get('start_time'):
                status['start_time'] = status['start_time'].isoformat()
            if status.get('estimated_completion'):
                status['estimated_completion'] = status['estimated_completion'].isoformat()
                
            # Calculate progress percentage
            if status['total_items'] > 0:
                status['progress_percent'] = (status['processed_items'] / status['total_items']) * 100
            else:
                status['progress_percent'] = 0
                
            return status
    
    def cancel_sync(self) -> bool:
        """Cancel ongoing synchronization."""
        with self.sync_lock:
            if self.is_syncing:
                self.is_syncing = False
                self.sync_progress['status'] = 'cancelled'
                logger.info("Sync cancellation requested")
                return True
            return False

class DiscogsClient:
    """
    Main Discogs API client with comprehensive features:
    - Secure token management
    - Rate limiting and retry logic
    - Collection fetching and parsing
    - Database integration
    - Offline mode support
    - Background synchronization
    """
    
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.rate_limiter = DiscogsRateLimiter()
        self.session = DiscogsSession()
        self.syncer = DiscogsCollectionSyncer(self)
        self._client = None
        self._user = None
        self._offline_mode = False
        
        # Cache for frequently accessed data
        self._collection_cache = {}
        self._cache_expiry = None
        
    def initialize(self, username: str, encrypted_token: str, encryption_key: bytes) -> bool:
        """
        Initialize the client with user credentials.
        
        Args:
            username: Discogs username
            encrypted_token: Encrypted user token
            encryption_key: Encryption key for token decryption
            
        Returns:
            bool: True if initialization successful
        """
        try:
            # Decrypt token
            f = Fernet(encryption_key)
            token = f.decrypt(encrypted_token.encode()).decode()
            
            # Initialize Discogs client
            self._client = discogs_client.Client(
                Config.DISCOGS_USER_AGENT,
                user_token=token
            )
            
            # Test connection and get user
            self._user = self._client.user(username)
            
            # Test API access with a simple call
            identity = self._client.identity()
            logger.info(f"Discogs client initialized for user: {identity.username}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Discogs client: {str(e)}")
            self._offline_mode = True
            return False
    
    def initialize_simple(self, username: str, token: str) -> bool:
        """
        Initialize the client with plain token (no encryption).
        
        Args:
            username: Discogs username
            token: Plain Discogs user token
            
        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize Discogs client
            self._client = discogs_client.Client(
                Config.DISCOGS_USER_AGENT,
                user_token=token
            )
            
            # Test connection and get user
            self._user = self._client.user(username)
            
            # Test API access with a simple call
            identity = self._client.identity()
            logger.info(f"Discogs client initialized for user: {identity.username}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Discogs client: {str(e)}")
            self._offline_mode = True
            return False
    
    def is_online(self) -> bool:
        """Check if client is online and functional."""
        return self._client is not None and not self._offline_mode
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the Discogs API connection.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.is_online():
            return False, "Client not initialized or in offline mode"
        
        try:
            self.rate_limiter.wait_if_needed()
            identity = self._client.identity()
            return True, f"Connected as {identity.username}"
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False, str(e)
    
    @lru_cache(maxsize=1)
    def _get_collection_info(self) -> Dict[str, Any]:
        """Get basic collection information (cached)."""
        if not self.is_online():
            raise DiscogsConnectionError("Client offline")
        
        try:
            self.rate_limiter.wait_if_needed()
            collection = self._user.collection_folders[0]  # "All" folder
            
            return {
                'count': collection.count,
                'name': collection.name,
                'id': collection.id
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {str(e)}")
            raise DiscogsAPIError(f"Collection info error: {str(e)}")
    
    def _fetch_collection_pages(self) -> Iterator[List[Dict[str, Any]]]:
        """
        Generator that yields collection pages.
        
        Yields:
            List of collection items for each page
        """
        if not self.is_online():
            raise DiscogsConnectionError("Client offline")
        
        try:
            collection = self._user.collection_folders[0]  # "All" folder
            page = 1
            
            while True:
                logger.info(f"Fetching collection page {page}")
                self.rate_limiter.wait_if_needed()
                
                try:
                    releases = collection.releases.page(page)
                    
                    if not releases:
                        break
                    
                    # Convert to list of dictionaries
                    page_items = []
                    for release in releases:
                        item_data = self._extract_release_data(release)
                        if item_data:
                            page_items.append(item_data)
                    
                    if page_items:
                        yield page_items
                        page += 1
                    else:
                        break
                        
                except Exception as e:
                    logger.error(f"Error fetching page {page}: {str(e)}")
                    if "not found" in str(e).lower():
                        break
                    raise
                
        except Exception as e:
            logger.error(f"Collection fetch error: {str(e)}")
            raise DiscogsAPIError(f"Failed to fetch collection: {str(e)}")
    
    def _extract_release_data(self, release) -> Optional[Dict[str, Any]]:
        """
        Extract and normalize release data.
        
        Args:
            release: Discogs release object
            
        Returns:
            Dictionary with normalized release data or None if extraction fails
        """
        try:
            # Get basic release info
            basic_info = release.release
            
            # Extract images - collection items might have thumb URL directly
            images = []
            
            # First try to get thumb from the collection item itself
            if hasattr(release, 'basic_information'):
                basic = release.basic_information
                if hasattr(basic, 'thumb') and basic.thumb:
                    images.append({
                        'type': 'primary',
                        'uri': basic.thumb,
                        'uri150': basic.thumb,
                        'uri600': basic.thumb
                    })
                elif hasattr(basic, 'cover_image') and basic.cover_image:
                    images.append({
                        'type': 'primary', 
                        'uri': basic.cover_image,
                        'uri150': basic.cover_image,
                        'uri600': basic.cover_image
                    })
            
            # If no thumb from basic info, try the full release data
            if not images and hasattr(basic_info, 'images') and basic_info.images:
                for img in basic_info.images:
                    if hasattr(img, 'uri'):
                        images.append({
                            'type': getattr(img, 'type', 'primary'),
                            'uri': img.uri,
                            'uri150': getattr(img, 'uri150', img.uri),
                            'uri600': getattr(img, 'uri600', img.uri)
                        })
            
            # Extract tracklist
            tracklist = []
            if hasattr(basic_info, 'tracklist') and basic_info.tracklist:
                for track in basic_info.tracklist:
                    tracklist.append({
                        'position': getattr(track, 'position', ''),
                        'title': getattr(track, 'title', ''),
                        'duration': getattr(track, 'duration', '')
                    })
            
            # Extract genres and styles
            genres = getattr(basic_info, 'genres', []) or []
            styles = getattr(basic_info, 'styles', []) or []
            
            # Extract artist information
            artist_name = "Various Artists"
            if hasattr(basic_info, 'artists') and basic_info.artists:
                artist_name = basic_info.artists[0].name
            
            # Get collection-specific data
            date_added = None
            rating = None
            notes = ""
            
            if hasattr(release, 'date_added'):
                date_added = release.date_added
            if hasattr(release, 'rating'):
                rating = release.rating
            if hasattr(release, 'notes'):
                notes_data = release.notes or ""
                # Ensure notes is always a string, not a list
                if isinstance(notes_data, list):
                    notes = "\n".join(str(n) for n in notes_data)
                else:
                    notes = str(notes_data) if notes_data else ""
            
            return {
                'discogs_id': basic_info.id,
                'title': getattr(basic_info, 'title', 'Unknown Title'),
                'artist': artist_name,
                'year': getattr(basic_info, 'year', 0) or 0,
                'genres': genres,
                'styles': styles,
                'images': images,
                'tracklist': tracklist,
                'notes': notes,
                'rating': rating,
                'date_added': date_added.isoformat() if date_added else datetime.now().isoformat(),
                'folder_id': getattr(release, 'folder_id', 0)
            }
            
        except Exception as e:
            logger.error(f"Error extracting release data for {getattr(release, 'id', 'unknown')}: {str(e)}")
            return None
    
    def _process_collection_item(self, item_data: Dict[str, Any]) -> bool:
        """
        Process and store a collection item in the database.
        
        Args:
            item_data: Normalized item data
            
        Returns:
            bool: True if processing successful
        """
        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            
            # Prepare data for database storage
            cover_url = None
            if item_data['images']:
                # Use the best available image
                primary_image = next(
                    (img for img in item_data['images'] if img['type'] == 'primary'),
                    item_data['images'][0] if item_data['images'] else None
                )
                if primary_image:
                    # Prefer higher resolution, fallback to any available
                    cover_url = primary_image.get('uri600') or primary_image.get('uri150') or primary_image.get('uri')
            
            # Insert or update album
            cursor.execute("""
                INSERT OR REPLACE INTO albums (
                    discogs_id, title, artist, year, cover_url,
                    genres, styles, tracklist, notes, rating,
                    date_added, folder_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_data['discogs_id'],
                item_data['title'],
                item_data['artist'],
                item_data['year'],
                cover_url,
                json.dumps(item_data['genres']),
                json.dumps(item_data['styles']),
                json.dumps(item_data['tracklist']),
                item_data['notes'],
                item_data['rating'],
                item_data['date_added'],
                item_data['folder_id']
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Processed album: {item_data['artist']} - {item_data['title']}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing item {item_data.get('discogs_id', 'unknown')}: {str(e)}")
            return False
    

    def _update_sync_log(self, items_synced: int, status: str):
        """Update the sync log with current progress."""
        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO sync_log (items_synced, status)
                VALUES (?, ?)
            """, (items_synced, status))
            
            # Update user's last sync time
            cursor.execute("""
                UPDATE users SET 
                    last_sync = CURRENT_TIMESTAMP,
                    total_items = ?
                WHERE id = 1
            """, (items_synced,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating sync log: {str(e)}")
    
    def sync_collection(self, background: bool = True, force_full: bool = False) -> bool:
        """
        Synchronize the user's collection.
        
        Args:
            background: Whether to run sync in background
            force_full: Force a full sync even if recent sync exists
            
        Returns:
            bool: True if sync started successfully
        """
        if not self.is_online():
            logger.warning("Cannot sync: client offline")
            return False
        
        if background:
            return self.syncer.start_background_sync(force_full)
        else:
            # Synchronous sync (not recommended for large collections)
            try:
                total_synced = 0
                for page_items in self._fetch_collection_pages():
                    for item in page_items:
                        if self._process_collection_item(item):
                            total_synced += 1
                
                self._update_sync_log(total_synced, 'completed')
                logger.info(f"Synchronous sync completed: {total_synced} items")
                return True
                
            except Exception as e:
                logger.error(f"Synchronous sync failed: {str(e)}")
                self._update_sync_log(0, 'failed')
                return False
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current synchronization status."""
        return self.syncer.get_sync_status()
    
    def cancel_sync(self) -> bool:
        """Cancel ongoing synchronization."""
        return self.syncer.cancel_sync()
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics from local database.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            
            # Basic counts
            cursor.execute("SELECT COUNT(*) as total FROM albums")
            total_albums = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT artist) as total FROM albums")
            total_artists = cursor.fetchone()[0]
            
            # Last sync info
            cursor.execute("""
                SELECT sync_time, items_synced, status 
                FROM sync_log 
                ORDER BY sync_time DESC 
                LIMIT 1
            """)
            last_sync = cursor.fetchone()
            
            # Genre distribution
            cursor.execute("""
                SELECT genres, COUNT(*) as count 
                FROM albums 
                WHERE genres IS NOT NULL AND genres != '[]'
                GROUP BY genres 
                ORDER BY count DESC 
                LIMIT 10
            """)
            genre_data = cursor.fetchall()
            
            conn.close()
            
            return {
                'total_albums': total_albums,
                'total_artists': total_artists,
                'last_sync': {
                    'time': last_sync[0] if last_sync else None,
                    'items': last_sync[1] if last_sync else 0,
                    'status': last_sync[2] if last_sync else 'never'
                },
                'top_genres': [
                    {'genres': json.loads(row[0]), 'count': row[1]} 
                    for row in genre_data
                ],
                'is_online': self.is_online()
            }
            
        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {
                'total_albums': 0,
                'total_artists': 0,
                'last_sync': {'time': None, 'items': 0, 'status': 'error'},
                'top_genres': [],
                'is_online': self.is_online()
            }
    
    def search_releases(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for releases on Discogs (online only).
        
        Args:
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of search results
        """
        if not self.is_online():
            return []
        
        try:
            self.rate_limiter.wait_if_needed()
            results = self._client.search(query, type='release')
            
            search_results = []
            for i, result in enumerate(results):
                if i >= limit:
                    break
                
                try:
                    search_results.append({
                        'id': result.id,
                        'title': getattr(result, 'title', 'Unknown'),
                        'artist': getattr(result, 'artist', 'Unknown'),
                        'year': getattr(result, 'year', None),
                        'format': getattr(result, 'format', []),
                        'label': getattr(result, 'label', []),
                        'thumb': getattr(result, 'thumb', '')
                    })
                except Exception as e:
                    logger.error(f"Error processing search result: {str(e)}")
                    continue
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search error: {str(e)}")
            return []
    
    def get_release_details(self, release_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific release.
        
        Args:
            release_id: Discogs release ID
            
        Returns:
            Release details or None if not found
        """
        if not self.is_online():
            return None
        
        try:
            self.rate_limiter.wait_if_needed()
            release = self._client.release(release_id)
            return self._extract_release_data(release)
            
        except Exception as e:
            logger.error(f"Error getting release details for {release_id}: {str(e)}")
            return None
    
    def cleanup_cache(self):
        """Clean up internal caches."""
        self._collection_cache.clear()
        self._cache_expiry = None
        # Clear LRU cache
        self._get_collection_info.cache_clear()
    
    def close(self):
        """Clean up resources."""
        if hasattr(self.session, 'session'):
            self.session.session.close()
        self.cleanup_cache()
        logger.info("Discogs client closed")

# Factory function for easy initialization
def create_discogs_client(database_path: Path, username: str = None, 
                         encrypted_token: str = None, encryption_key: bytes = None) -> DiscogsClient:
    """
    Factory function to create and optionally initialize a Discogs client.
    
    Args:
        database_path: Path to SQLite database
        username: Discogs username (optional)
        encrypted_token: Encrypted user token (optional)
        encryption_key: Encryption key (optional)
        
    Returns:
        DiscogsClient instance
    """
    client = DiscogsClient(database_path)
    
    if username and encrypted_token and encryption_key:
        client.initialize(username, encrypted_token, encryption_key)
    
    return client

# Utility functions for integration with Flask app
def get_user_discogs_data(db_connection) -> Optional[Tuple[str, str]]:
    """
    Get user's Discogs credentials from database.
    
    Args:
        db_connection: SQLite database connection
        
    Returns:
        Tuple of (username, encrypted_token) or None
    """
    try:
        cursor = db_connection.execute(
            "SELECT discogs_username, user_token FROM users LIMIT 1"
        )
        result = cursor.fetchone()
        
        if result:
            return result['discogs_username'], result['user_token']
        return None
        
    except Exception as e:
        logger.error(f"Error getting user Discogs data: {str(e)}")
        return None

def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (doubles each time)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (DiscogsRateLimitError, DiscogsConnectionError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = delay * (2 ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed")
                        break
                except Exception as e:
                    # Don't retry on non-recoverable errors
                    logger.error(f"Non-recoverable error: {str(e)}")
                    raise
            
            # If we get here, all retries failed
            raise last_exception or DiscogsAPIError("All retry attempts failed")
        
        return wrapper
    return decorator

# Module-level client instance for Flask app integration
_global_client: Optional[DiscogsClient] = None

def get_global_client() -> Optional[DiscogsClient]:
    """Get the global client instance."""
    return _global_client

def initialize_global_client_simple(database_path: Path, username: str, token: str) -> bool:
    """
    Initialize the global client instance with plain token.
    
    Args:
        database_path: Path to SQLite database
        username: Discogs username
        token: Plain Discogs user token
        
    Returns:
        bool: True if initialization successful
    """
    global _global_client
    
    try:
        _global_client = create_discogs_client(database_path)
        success = _global_client.initialize_simple(username, token)
        logger.info("Global Discogs client initialized")
        return success
        
    except Exception as e:
        logger.error(f"Failed to initialize global client: {str(e)}")
        return False

def initialize_global_client(database_path: Path, username: str = None,
                           encrypted_token: str = None, encryption_key: bytes = None) -> bool:
    """
    Initialize the global client instance.
    
    Args:
        database_path: Path to SQLite database
        username: Discogs username (optional)
        encrypted_token: Encrypted user token (optional)
        encryption_key: Encryption key (optional)
        
    Returns:
        bool: True if initialization successful
    """
    global _global_client
    
    try:
        _global_client = create_discogs_client(
            database_path, username, encrypted_token, encryption_key
        )
        logger.info("Global Discogs client initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize global client: {str(e)}")
        return False

def shutdown_global_client():
    """Shutdown the global client instance."""
    global _global_client
    
    if _global_client:
        _global_client.close()
        _global_client = None
        logger.info("Global Discogs client shutdown")

# Example usage and testing functions
if __name__ == "__main__":
    # This section can be used for testing the module
    logging.basicConfig(level=logging.INFO)
    
    # Example usage:
    # client = create_discogs_client(Path("test.db"))
    # success = client.initialize("username", "encrypted_token", b"encryption_key")
    # if success:
    #     print("Client initialized successfully")
    #     stats = client.get_collection_stats()
    #     print(f"Collection stats: {stats}")
    
    print("Discogs client module loaded successfully")