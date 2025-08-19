"""
Pytest configuration and shared fixtures for VinylVault test suite.
"""

import pytest
import tempfile
import sqlite3
import os
import shutil
import time
from pathlib import Path
from unittest.mock import Mock, patch
from flask import Flask
from cryptography.fernet import Fernet

# Import application modules
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from config import Config
from discogs_client import create_discogs_client
from image_cache import ImageCache
from random_algorithm import RandomAlgorithm

@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
def test_config(temp_dir):
    """Create test configuration."""
    config = Config()
    config.DATABASE_PATH = temp_dir / "test_vinylvault.db"
    config.CACHE_DIR = temp_dir / "cache"
    config.COVERS_DIR = temp_dir / "cache" / "covers"
    config.LOG_FILE = temp_dir / "test_vinylvault.log"
    config.SECRET_KEY = "test-secret-key"
    config.TESTING = True
    config.WTF_CSRF_ENABLED = False
    
    # Create directories
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.COVERS_DIR.mkdir(parents=True, exist_ok=True)
    
    return config

@pytest.fixture
def test_db(test_config):
    """Create and initialize test database."""
    # Initialize database schema
    from init_db import create_database_schema
    create_database_schema(test_config.DATABASE_PATH)
    
    conn = sqlite3.connect(str(test_config.DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()

@pytest.fixture
def app(test_config):
    """Create Flask test application."""
    with patch('config.Config', return_value=test_config):
        app = create_app(test_config)
        app.config.update({
            'TESTING': True,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret-key'
        })
    yield app

@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Create Flask CLI test runner."""
    return app.test_cli_runner()

@pytest.fixture
def mock_discogs_client():
    """Create mock Discogs client."""
    client = Mock()
    client.is_online.return_value = True
    client.get_user_collection.return_value = []
    client.get_collection_stats.return_value = {
        'total_albums': 0,
        'total_artists': 0,
        'genres': {},
        'decades': {},
        'avg_rating': 0
    }
    client.search_albums.return_value = []
    client.get_album_details.return_value = None
    return client

@pytest.fixture
def sample_album_data():
    """Sample album data for testing."""
    return {
        'discogs_id': 123456,
        'title': 'Test Album',
        'artist': 'Test Artist',
        'year': 2023,
        'genre': 'Rock',
        'style': 'Alternative Rock',
        'label': 'Test Records',
        'catno': 'TEST001',
        'format': 'LP',
        'country': 'US',
        'thumb_url': 'https://example.com/thumb.jpg',
        'cover_url': 'https://example.com/cover.jpg',
        'rating': 4,
        'user_rating': 5,
        'notes': 'Great album!',
        'date_added': '2023-01-01',
        'last_synced': '2023-01-01'
    }

@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    key = Fernet.generate_key()
    f = Fernet(key)
    return {
        'username': 'testuser',
        'token': 'test_token',
        'encrypted_token': f.encrypt(b'test_token'),
        'encryption_key': key,
        'setup_completed': True
    }

@pytest.fixture
def authenticated_session(client, sample_user_data):
    """Create authenticated session."""
    with client.session_transaction() as sess:
        sess['username'] = sample_user_data['username']
        sess['encryption_key'] = sample_user_data['encryption_key']
        sess['setup_completed'] = True

@pytest.fixture
def mock_image_cache(test_config):
    """Create mock image cache."""
    cache = Mock(spec=ImageCache)
    cache.get_cached_image_url.return_value = 'https://example.com/cached_image.jpg'
    cache.cache_image.return_value = True
    cache.get_cache_stats.return_value = {
        'total_images': 0,
        'cache_size_mb': 0,
        'hit_rate': 0.0
    }
    return cache

@pytest.fixture
def performance_timer():
    """Timer fixture for performance testing."""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return Timer()

@pytest.fixture(scope="session")
def docker_services():
    """Setup Docker services for testing."""
    import docker
    try:
        client = docker.from_env()
        # Check if Docker is available
        client.ping()
        yield client
    except Exception:
        pytest.skip("Docker not available")

# Custom markers for test categorization
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "deployment: Deployment tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "docker: Tests requiring Docker")
    config.addinivalue_line("markers", "api: API endpoint tests")

def pytest_collection_modifyitems(config, items):
    """Modify test collection to add default markers."""
    for item in items:
        # Add slow marker to tests that take > 5 seconds
        if "slow" not in item.keywords:
            item.add_marker(pytest.mark.timeout(5))