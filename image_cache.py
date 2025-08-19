#!/usr/bin/env python3
"""
VinylVault Image Caching System

A comprehensive image caching system with:
- WebP optimization with 85% quality
- Multi-size caching (150px thumbnails, 600px detail view)
- LRU eviction with 2GB cache limit
- Lazy loading with placeholder support
- Raspberry Pi memory optimization
- Thread-safe operations
- Background processing
- Error handling and fallback support
- Integration with Discogs image URLs
"""

import os
import time
import hashlib
import sqlite3
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Union
from dataclasses import dataclass, asdict
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
import gc

import requests
from PIL import Image, ImageOps
from PIL import ExifTags
import io

from config import Config

# Configure module-specific logging
logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Represents a cached image entry with metadata."""
    file_path: str
    original_url: str
    size_type: str  # 'thumbnail' or 'detail'
    file_size: int
    created_at: datetime
    last_accessed: datetime
    access_count: int
    width: int
    height: int
    format: str = 'WEBP'

@dataclass
class CacheStats:
    """Cache statistics for monitoring."""
    total_entries: int
    total_size_bytes: int
    thumbnail_count: int
    detail_count: int
    hit_rate: float
    cache_limit_bytes: int
    available_space_bytes: int
    last_cleanup: Optional[datetime]
    
class ImageProcessingError(Exception):
    """Custom exception for image processing errors."""
    pass

class CacheLimitError(Exception):
    """Exception for cache limit exceeded."""
    pass

class MemoryOptimizedProcessor:
    """Memory-efficient image processor optimized for Raspberry Pi."""
    
    # Maximum image dimensions to prevent memory issues
    MAX_ORIGINAL_SIZE = (2048, 2048)
    THUMBNAIL_SIZE = (150, 150)
    DETAIL_SIZE = (600, 600)
    WEBP_QUALITY = 85
    
    @staticmethod
    def process_image(image_data: bytes, target_size: Tuple[int, int], 
                     optimize_memory: bool = True) -> bytes:
        """
        Process image data to WebP format with specified size.
        
        Args:
            image_data: Raw image bytes
            target_size: Target dimensions (width, height)
            optimize_memory: Enable memory optimizations for Pi
            
        Returns:
            Processed WebP image bytes
        """
        try:
            # Force garbage collection before processing
            if optimize_memory:
                gc.collect()
            
            # Open image with memory-efficient loading
            with Image.open(io.BytesIO(image_data)) as img:
                # Handle EXIF orientation
                img = ImageOps.exif_transpose(img)
                
                # Convert to RGB if necessary (WebP doesn't support transparency well)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background for transparency
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize with high-quality resampling
                original_size = img.size
                
                # Calculate resize dimensions maintaining aspect ratio
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
                
                # Save to WebP format
                output = io.BytesIO()
                img.save(output, 
                        format='WEBP',
                        quality=MemoryOptimizedProcessor.WEBP_QUALITY,
                        optimize=True,
                        method=6)  # Best compression
                
                processed_data = output.getvalue()
                
                # Force cleanup
                if optimize_memory:
                    del img, output
                    gc.collect()
                
                return processed_data
                
        except Exception as e:
            logger.error(f"Image processing failed: {str(e)}")
            raise ImageProcessingError(f"Failed to process image: {str(e)}")

class LRUCache:
    """Thread-safe LRU cache implementation with size limits."""
    
    def __init__(self, max_size_bytes: int = 2 * 1024 * 1024 * 1024):  # 2GB default
        self.max_size_bytes = max_size_bytes
        self.current_size_bytes = 0
        self.cache_order = OrderedDict()  # key -> last_access_time
        self.cache_data = {}  # key -> CacheEntry
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_requests': 0
        }
    
    def get(self, key: str) -> Optional[CacheEntry]:
        """Get cache entry and update access time."""
        with self.lock:
            self.stats['total_requests'] += 1
            
            if key in self.cache_data:
                # Update access time and move to end (most recent)
                entry = self.cache_data[key]
                entry.last_accessed = datetime.now()
                entry.access_count += 1
                
                # Move to end of OrderedDict
                self.cache_order.move_to_end(key)
                
                self.stats['hits'] += 1
                return entry
            else:
                self.stats['misses'] += 1
                return None
    
    def put(self, key: str, entry: CacheEntry) -> bool:
        """Add entry to cache, evicting if necessary."""
        with self.lock:
            # If key already exists, remove old entry first
            if key in self.cache_data:
                old_entry = self.cache_data[key]
                self.current_size_bytes -= old_entry.file_size
                del self.cache_data[key]
                del self.cache_order[key]
            
            # Check if we need to evict entries
            while (self.current_size_bytes + entry.file_size > self.max_size_bytes and 
                   self.cache_order):
                self._evict_lru()
            
            # Check if single entry is too large
            if entry.file_size > self.max_size_bytes:
                logger.warning(f"Entry too large for cache: {entry.file_size} bytes")
                return False
            
            # Add new entry
            self.cache_data[key] = entry
            self.cache_order[key] = entry.last_accessed
            self.current_size_bytes += entry.file_size
            
            return True
    
    def _evict_lru(self):
        """Evict least recently used entry."""
        if not self.cache_order:
            return
        
        # Get LRU key (first item)
        lru_key = next(iter(self.cache_order))
        lru_entry = self.cache_data[lru_key]
        
        # Remove from cache
        del self.cache_data[lru_key]
        del self.cache_order[lru_key]
        self.current_size_bytes -= lru_entry.file_size
        self.stats['evictions'] += 1
        
        # Remove file from disk
        try:
            if os.path.exists(lru_entry.file_path):
                os.remove(lru_entry.file_path)
                logger.debug(f"Evicted cache file: {lru_entry.file_path}")
        except Exception as e:
            logger.error(f"Failed to remove evicted file {lru_entry.file_path}: {e}")
    
    def remove(self, key: str) -> bool:
        """Remove specific entry from cache."""
        with self.lock:
            if key in self.cache_data:
                entry = self.cache_data[key]
                self.current_size_bytes -= entry.file_size
                del self.cache_data[key]
                del self.cache_order[key]
                
                # Remove file from disk
                try:
                    if os.path.exists(entry.file_path):
                        os.remove(entry.file_path)
                except Exception as e:
                    logger.error(f"Failed to remove cache file {entry.file_path}: {e}")
                
                return True
            return False
    
    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            for entry in self.cache_data.values():
                try:
                    if os.path.exists(entry.file_path):
                        os.remove(entry.file_path)
                except Exception as e:
                    logger.error(f"Failed to remove cache file {entry.file_path}: {e}")
            
            self.cache_data.clear()
            self.cache_order.clear()
            self.current_size_bytes = 0
            self.stats = {'hits': 0, 'misses': 0, 'evictions': 0, 'total_requests': 0}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            hit_rate = (self.stats['hits'] / max(self.stats['total_requests'], 1)) * 100
            
            return {
                'entries': len(self.cache_data),
                'size_bytes': self.current_size_bytes,
                'max_size_bytes': self.max_size_bytes,
                'hit_rate': hit_rate,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'evictions': self.stats['evictions'],
                'total_requests': self.stats['total_requests']
            }

class ImageCache:
    """
    Main image caching system with comprehensive features.
    """
    
    def __init__(self, cache_dir: Path, database_path: Path, 
                 max_cache_size: int = 2 * 1024 * 1024 * 1024):
        """
        Initialize image cache.
        
        Args:
            cache_dir: Directory for cached images
            database_path: SQLite database path for metadata
            max_cache_size: Maximum cache size in bytes (default 2GB)
        """
        self.cache_dir = Path(cache_dir)
        self.database_path = Path(database_path)
        self.max_cache_size = max_cache_size
        
        # Create cache directories
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / 'thumbnails').mkdir(exist_ok=True)
        (self.cache_dir / 'detail').mkdir(exist_ok=True)
        
        # Initialize components
        self.lru_cache = LRUCache(max_cache_size)
        self.processor = MemoryOptimizedProcessor()
        self.download_session = self._create_session()
        
        # Thread pool for background processing
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ImageCache")
        
        # Initialize cache database
        self._init_cache_database()
        
        # Load existing cache entries
        self._load_cache_from_database()
        
        logger.info(f"Image cache initialized: {cache_dir}, max size: {max_cache_size / (1024*1024):.1f}MB")
    
    def _create_session(self) -> requests.Session:
        """Create optimized requests session."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': Config.DISCOGS_USER_AGENT,
            'Accept': 'image/webp,image/jpeg,image/png,image/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate'
        })
        
        # Configure for Pi - smaller connection pool
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=2,
            pool_maxsize=4,
            max_retries=3
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        return session
    
    def _init_cache_database(self):
        """Initialize cache metadata database."""
        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS image_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE NOT NULL,
                    original_url TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    size_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    format TEXT DEFAULT 'WEBP'
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_key ON image_cache(cache_key)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_accessed ON image_cache(last_accessed)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_size_type ON image_cache(size_type)
            """)
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize cache database: {e}")
            raise
    
    def _load_cache_from_database(self):
        """Load existing cache entries from database into memory."""
        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM image_cache ORDER BY last_accessed DESC
            """)
            
            loaded_count = 0
            for row in cursor.fetchall():
                cache_key = row['cache_key']
                file_path = row['file_path']
                
                # Check if file still exists
                if os.path.exists(file_path):
                    entry = CacheEntry(
                        file_path=file_path,
                        original_url=row['original_url'],
                        size_type=row['size_type'],
                        file_size=row['file_size'],
                        created_at=datetime.fromisoformat(row['created_at']),
                        last_accessed=datetime.fromisoformat(row['last_accessed']),
                        access_count=row['access_count'],
                        width=row['width'],
                        height=row['height'],
                        format=row['format']
                    )
                    
                    if self.lru_cache.put(cache_key, entry):
                        loaded_count += 1
                else:
                    # Remove orphaned database entry
                    cursor.execute("DELETE FROM image_cache WHERE id = ?", (row['id'],))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Loaded {loaded_count} existing cache entries")
            
        except Exception as e:
            logger.error(f"Failed to load cache from database: {e}")
    
    def _generate_cache_key(self, url: str, size_type: str) -> str:
        """Generate unique cache key for URL and size type."""
        content = f"{url}:{size_type}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_cache_file_path(self, cache_key: str, size_type: str) -> Path:
        """Get file path for cached image."""
        return self.cache_dir / size_type / f"{cache_key}.webp"
    
    def _download_image(self, url: str, timeout: int = 30) -> bytes:
        """Download image from URL with error handling."""
        try:
            response = self.download_session.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                raise ImageProcessingError(f"Invalid content type: {content_type}")
            
            # Download with size limit (10MB max)
            max_size = 10 * 1024 * 1024
            content = b''
            
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > max_size:
                    raise ImageProcessingError("Image too large")
            
            return content
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download image from {url}: {e}")
            raise ImageProcessingError(f"Download failed: {e}")
    
    def _save_cache_entry(self, cache_key: str, entry: CacheEntry):
        """Save cache entry to database."""
        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO image_cache (
                    cache_key, original_url, file_path, size_type, file_size,
                    created_at, last_accessed, access_count, width, height, format
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cache_key, entry.original_url, entry.file_path, entry.size_type,
                entry.file_size, entry.created_at.isoformat(), 
                entry.last_accessed.isoformat(), entry.access_count,
                entry.width, entry.height, entry.format
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to save cache entry to database: {e}")
    
    def _process_and_cache_image(self, url: str, size_type: str) -> Optional[CacheEntry]:
        """Download, process, and cache an image."""
        cache_key = self._generate_cache_key(url, size_type)
        file_path = self._get_cache_file_path(cache_key, size_type)
        
        try:
            # Download image
            logger.debug(f"Downloading image: {url}")
            image_data = self._download_image(url)
            
            # Determine target size
            target_size = (
                self.processor.THUMBNAIL_SIZE if size_type == 'thumbnails'
                else self.processor.DETAIL_SIZE
            )
            
            # Process image
            logger.debug(f"Processing image for {size_type}")
            processed_data = self.processor.process_image(image_data, target_size)
            
            # Get image dimensions
            with Image.open(io.BytesIO(processed_data)) as img:
                width, height = img.size
            
            # Save to disk
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(processed_data)
            
            # Create cache entry
            now = datetime.now()
            entry = CacheEntry(
                file_path=str(file_path),
                original_url=url,
                size_type=size_type,
                file_size=len(processed_data),
                created_at=now,
                last_accessed=now,
                access_count=1,
                width=width,
                height=height,
                format='WEBP'
            )
            
            # Add to cache and database
            if self.lru_cache.put(cache_key, entry):
                self._save_cache_entry(cache_key, entry)
                logger.debug(f"Cached image: {url} -> {file_path}")
                return entry
            else:
                # Failed to add to cache (too large), remove file
                if file_path.exists():
                    file_path.unlink()
                logger.warning(f"Image too large for cache: {url}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to process and cache image {url}: {e}")
            # Clean up partial file
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            return None
    
    def get_image(self, url: str, size_type: str = 'detail') -> Optional[str]:
        """
        Get cached image path, downloading and processing if necessary.
        
        Args:
            url: Original image URL
            size_type: 'thumbnails' or 'detail'
            
        Returns:
            Path to cached image file or None if failed
        """
        if not url:
            return None
        
        cache_key = self._generate_cache_key(url, size_type)
        
        # Check cache first
        entry = self.lru_cache.get(cache_key)
        if entry and os.path.exists(entry.file_path):
            # Update database access time
            self._save_cache_entry(cache_key, entry)
            return entry.file_path
        
        # Image not in cache or file missing, process it
        entry = self._process_and_cache_image(url, size_type)
        return entry.file_path if entry else None
    
    def get_image_async(self, url: str, size_type: str = 'detail') -> 'Future':
        """
        Get image asynchronously for background processing.
        
        Args:
            url: Original image URL
            size_type: 'thumbnails' or 'detail'
            
        Returns:
            Future object that will resolve to image path or None
        """
        return self.executor.submit(self.get_image, url, size_type)
    
    def preload_images(self, urls: List[str], progress_callback=None) -> Dict[str, bool]:
        """
        Preload multiple images in background.
        
        Args:
            urls: List of image URLs to preload
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary mapping URLs to success status
        """
        results = {}
        total_urls = len(urls)
        
        # Submit all tasks
        future_to_url = {}
        for url in urls:
            if url:  # Skip empty URLs
                # Preload both sizes
                future_thumb = self.executor.submit(self.get_image, url, 'thumbnails')
                future_detail = self.executor.submit(self.get_image, url, 'detail')
                future_to_url[future_thumb] = (url, 'thumbnails')
                future_to_url[future_detail] = (url, 'detail')
        
        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_url):
            url, size_type = future_to_url[future]
            try:
                result = future.result()
                success = result is not None
                
                # Track overall success per URL
                if url not in results:
                    results[url] = True
                results[url] = results[url] and success
                
                if size_type == 'detail':  # Count completion when detail is done
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total_urls, url)
                        
            except Exception as e:
                logger.error(f"Failed to preload {url} ({size_type}): {e}")
                if url not in results:
                    results[url] = False
                results[url] = False
        
        return results
    
    def get_placeholder_path(self, size_type: str = 'detail') -> str:
        """
        Get path to placeholder image for loading states.
        
        Args:
            size_type: 'thumbnails' or 'detail'
            
        Returns:
            Path to placeholder image
        """
        # Create a simple colored placeholder if it doesn't exist
        placeholder_dir = self.cache_dir / 'placeholders'
        placeholder_dir.mkdir(exist_ok=True)
        
        size = (150, 150) if size_type == 'thumbnails' else (600, 600)
        placeholder_path = placeholder_dir / f"placeholder_{size_type}.webp"
        
        if not placeholder_path.exists():
            try:
                # Create a simple gradient placeholder
                img = Image.new('RGB', size, color=(240, 240, 240))
                
                # Add some texture
                from PIL import ImageDraw
                draw = ImageDraw.Draw(img)
                
                # Draw vinyl record-like circles
                center_x, center_y = size[0] // 2, size[1] // 2
                max_radius = min(size) // 2 - 10
                
                for i in range(0, max_radius, 20):
                    color = (220 - i // 4, 220 - i // 4, 220 - i // 4)
                    draw.ellipse([
                        center_x - i, center_y - i,
                        center_x + i, center_y + i
                    ], outline=color, width=2)
                
                # Add center dot
                draw.ellipse([
                    center_x - 5, center_y - 5,
                    center_x + 5, center_y + 5
                ], fill=(100, 100, 100))
                
                img.save(placeholder_path, 'WEBP', quality=85)
                logger.debug(f"Created placeholder: {placeholder_path}")
                
            except Exception as e:
                logger.error(f"Failed to create placeholder: {e}")
        
        return str(placeholder_path)
    
    def cleanup_cache(self, max_age_days: int = 30) -> int:
        """
        Clean up old cache entries.
        
        Args:
            max_age_days: Maximum age for cache entries
            
        Returns:
            Number of entries cleaned up
        """
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        cleaned_count = 0
        
        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get old entries
            cursor.execute("""
                SELECT cache_key, file_path FROM image_cache 
                WHERE last_accessed < ?
            """, (cutoff_date.isoformat(),))
            
            old_entries = cursor.fetchall()
            
            for row in old_entries:
                cache_key = row['cache_key']
                file_path = row['file_path']
                
                # Remove from LRU cache
                if self.lru_cache.remove(cache_key):
                    cleaned_count += 1
                
                # Remove from database
                cursor.execute("DELETE FROM image_cache WHERE cache_key = ?", (cache_key,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {cleaned_count} old cache entries")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
            return 0
    
    def get_cache_stats(self) -> CacheStats:
        """Get comprehensive cache statistics."""
        try:
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            
            # Get counts by type
            cursor.execute("""
                SELECT size_type, COUNT(*) as count 
                FROM image_cache 
                GROUP BY size_type
            """)
            type_counts = dict(cursor.fetchall())
            
            # Get total size
            cursor.execute("SELECT SUM(file_size) as total_size FROM image_cache")
            total_size = cursor.fetchone()[0] or 0
            
            # Get total entries
            cursor.execute("SELECT COUNT(*) as total FROM image_cache")
            total_entries = cursor.fetchone()[0]
            
            conn.close()
            
            # Get LRU cache stats
            lru_stats = self.lru_cache.get_stats()
            
            return CacheStats(
                total_entries=total_entries,
                total_size_bytes=total_size,
                thumbnail_count=type_counts.get('thumbnails', 0),
                detail_count=type_counts.get('detail', 0),
                hit_rate=lru_stats['hit_rate'],
                cache_limit_bytes=self.max_cache_size,
                available_space_bytes=self.max_cache_size - total_size,
                last_cleanup=None  # Could be tracked separately
            )
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return CacheStats(0, 0, 0, 0, 0.0, self.max_cache_size, self.max_cache_size, None)
    
    def clear_cache(self) -> bool:
        """Clear all cached images."""
        try:
            # Clear LRU cache (also removes files)
            self.lru_cache.clear()
            
            # Clear database
            conn = sqlite3.connect(str(self.database_path))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM image_cache")
            conn.commit()
            conn.close()
            
            # Remove any remaining files
            for subdir in ['thumbnails', 'detail']:
                cache_subdir = self.cache_dir / subdir
                if cache_subdir.exists():
                    for file_path in cache_subdir.glob('*.webp'):
                        try:
                            file_path.unlink()
                        except Exception as e:
                            logger.error(f"Failed to remove {file_path}: {e}")
            
            logger.info("Cache cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    def shutdown(self):
        """Shutdown cache system and cleanup resources."""
        try:
            self.executor.shutdown(wait=True, timeout=30)
            self.download_session.close()
            logger.info("Image cache shutdown complete")
        except Exception as e:
            logger.error(f"Error during cache shutdown: {e}")

# Global cache instance
_global_cache: Optional[ImageCache] = None

def get_image_cache() -> Optional[ImageCache]:
    """Get the global image cache instance."""
    return _global_cache

def initialize_image_cache(cache_dir: Path, database_path: Path, 
                          max_cache_size: int = 2 * 1024 * 1024 * 1024) -> bool:
    """
    Initialize the global image cache.
    
    Args:
        cache_dir: Directory for cached images
        database_path: SQLite database path
        max_cache_size: Maximum cache size in bytes
        
    Returns:
        bool: True if initialization successful
    """
    global _global_cache
    
    try:
        _global_cache = ImageCache(cache_dir, database_path, max_cache_size)
        logger.info("Global image cache initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize global image cache: {e}")
        return False

def shutdown_image_cache():
    """Shutdown the global image cache."""
    global _global_cache
    
    if _global_cache:
        _global_cache.shutdown()
        _global_cache = None
        logger.info("Global image cache shutdown")

# Utility functions for Flask integration
def get_cached_image_url(discogs_url: str, size_type: str = 'detail') -> Optional[str]:
    """
    Get cached image URL for use in templates.
    
    Args:
        discogs_url: Original Discogs image URL
        size_type: 'thumbnails' or 'detail'
        
    Returns:
        Relative URL to cached image or None
    """
    cache = get_image_cache()
    if not cache:
        return None
    
    cached_path = cache.get_image(discogs_url, size_type)
    if cached_path:
        # Convert absolute path to relative URL
        cache_rel_path = Path(cached_path).relative_to(cache.cache_dir)
        return f"/cache/{cache_rel_path}"
    
    return None

def get_placeholder_url(size_type: str = 'detail') -> str:
    """Get placeholder image URL."""
    cache = get_image_cache()
    if cache:
        placeholder_path = cache.get_placeholder_path(size_type)
        cache_rel_path = Path(placeholder_path).relative_to(cache.cache_dir)
        return f"/cache/{cache_rel_path}"
    
    # Fallback to static placeholder
    return "/static/vinyl-icon.svg"

# Example usage and testing
if __name__ == "__main__":
    # This section can be used for testing the module
    logging.basicConfig(level=logging.DEBUG)
    
    # Example usage:
    cache_dir = Path("cache/covers")
    db_path = Path("cache/vinylvault.db")
    
    # Initialize cache
    if initialize_image_cache(cache_dir, db_path, max_cache_size=100*1024*1024):  # 100MB for testing
        cache = get_image_cache()
        
        # Test with a sample URL (this would be a real Discogs image URL)
        test_url = "https://via.placeholder.com/600x600.jpg"
        
        print("Testing image cache...")
        
        # Get thumbnail
        thumb_path = cache.get_image(test_url, 'thumbnails')
        print(f"Thumbnail cached at: {thumb_path}")
        
        # Get detail image
        detail_path = cache.get_image(test_url, 'detail')
        print(f"Detail image cached at: {detail_path}")
        
        # Get stats
        stats = cache.get_cache_stats()
        print(f"Cache stats: {asdict(stats)}")
        
        # Cleanup
        shutdown_image_cache()
    
    print("Image cache module test complete")