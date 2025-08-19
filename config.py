import os
from pathlib import Path

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database settings
    BASE_DIR = Path(__file__).parent
    DATABASE_PATH = BASE_DIR / 'cache' / 'vinylvault.db'
    
    # Cache settings
    CACHE_DIR = BASE_DIR / 'cache'
    COVERS_DIR = CACHE_DIR / 'covers'
    MAX_CACHE_SIZE_GB = 2
    
    # Discogs API settings
    DISCOGS_USER_AGENT = 'VinylVault/1.0'
    RATE_LIMIT_DELAY = 1.1  # seconds between API calls
    DISCOGS_MAX_REQUESTS_PER_MINUTE = 55  # Conservative limit
    DISCOGS_REQUEST_TIMEOUT = (10, 30)  # (connect, read) timeouts
    DISCOGS_MAX_RETRIES = 3
    DISCOGS_RETRY_DELAY = 1.0  # Initial retry delay
    
    # UI settings
    ITEMS_PER_PAGE = 24
    GRID_COLUMNS_MIN = 2
    GRID_COLUMNS_MAX = 4
    
    # Touch settings
    MIN_TOUCH_TARGET = 44  # pixels
    
    # Image settings
    THUMBNAIL_SIZE = 150
    DETAIL_SIZE = 600
    IMAGE_QUALITY = 85
    
    # Sync settings
    SYNC_BATCH_SIZE = 100  # Items to process in each batch
    SYNC_PROGRESS_LOG_INTERVAL = 50  # Log progress every N items
    SYNC_MAX_ERRORS = 10  # Stop sync if more than N errors
    
    # Performance settings for Raspberry Pi
    MAX_CONCURRENT_DOWNLOADS = 3
    MEMORY_CACHE_SIZE_MB = 128
    DATABASE_WAL_MODE = True  # Enable WAL mode for better concurrency
    
    @classmethod
    def init_app(cls, app):
        # Ensure cache directories exist
        cls.CACHE_DIR.mkdir(exist_ok=True)
        cls.COVERS_DIR.mkdir(exist_ok=True)