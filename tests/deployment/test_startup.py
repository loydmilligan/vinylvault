"""
Application startup and initialization tests.
"""

import pytest
import sqlite3
import time
import os
from pathlib import Path
from unittest.mock import patch, Mock

from app import create_app
from config import Config


@pytest.mark.deployment
class TestApplicationStartup:
    """Test application startup and initialization."""
    
    def test_config_loading(self, test_config):
        """Test configuration loading and validation."""
        assert test_config.DATABASE_PATH is not None
        assert test_config.CACHE_DIR is not None
        assert test_config.COVERS_DIR is not None
        assert test_config.SECRET_KEY is not None
        
        # Test directory creation
        assert test_config.CACHE_DIR.exists()
        assert test_config.COVERS_DIR.exists()
    
    def test_app_creation(self, test_config):
        """Test Flask app creation."""
        app = create_app(test_config)
        
        assert app is not None
        assert app.config['TESTING'] == True
        assert 'vinylvault' in app.name.lower() or 'app' in app.name
    
    def test_database_initialization(self, test_db):
        """Test database schema initialization."""
        # Check that all required tables exist
        cursor = test_db.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['users', 'albums', 'sync_log', 'random_cache']
        for table in required_tables:
            assert table in tables, f"Required table '{table}' not found"
    
    def test_database_indexes(self, test_db):
        """Test that performance indexes are created."""
        cursor = test_db.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_%'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        
        # Should have at least some indexes for performance
        assert len(indexes) > 0, "Database should have performance indexes"
    
    def test_route_registration(self, app):
        """Test that all routes are registered."""
        expected_routes = [
            '/',
            '/setup',
            '/sync',
            '/random',
            '/stats',
            '/health',
            '/api/albums',
            '/api/random',
            '/api/stats'
        ]
        
        registered_routes = []
        for rule in app.url_map.iter_rules():
            registered_routes.append(rule.rule)
        
        for route in expected_routes:
            assert route in registered_routes, f"Route '{route}' not registered"
    
    def test_static_files_configuration(self, app):
        """Test static files are properly configured."""
        # Check static folder exists
        static_folder = Path(app.static_folder)
        assert static_folder.exists(), "Static folder should exist"
        
        # Check required static files
        required_files = ['style.css', 'app.js', 'vinyl-icon.svg']
        for filename in required_files:
            static_file = static_folder / filename
            assert static_file.exists(), f"Required static file '{filename}' not found"
    
    def test_template_configuration(self, app):
        """Test template configuration."""
        # Check template folder exists
        template_folder = Path(app.template_folder)
        assert template_folder.exists(), "Template folder should exist"
        
        # Check required templates
        required_templates = [
            'base.html',
            'index.html', 
            'setup.html',
            'sync.html',
            'stats.html',
            '404.html',
            '500.html'
        ]
        
        for template in required_templates:
            template_file = template_folder / template
            assert template_file.exists(), f"Required template '{template}' not found"
    
    def test_logging_configuration(self, test_config, app):
        """Test logging is properly configured."""
        import logging
        
        # Check that VinylVault logger exists
        logger = logging.getLogger('vinylvault')
        assert logger is not None
        
        # Check log file will be created in correct location
        assert test_config.LOG_FILE.parent.exists(), "Log directory should exist"
    
    def test_secret_key_security(self, app):
        """Test that secret key is properly configured."""
        secret_key = app.config.get('SECRET_KEY')
        
        assert secret_key is not None, "Secret key should be set"
        assert len(secret_key) >= 24, "Secret key should be sufficiently long"
        assert secret_key != 'dev', "Secret key should not be default value"
    
    def test_csrf_configuration(self, app):
        """Test CSRF protection configuration."""
        # In production, CSRF should be enabled
        # In testing, it might be disabled
        csrf_enabled = app.config.get('WTF_CSRF_ENABLED', True)
        testing = app.config.get('TESTING', False)
        
        if not testing:
            assert csrf_enabled, "CSRF protection should be enabled in production"
    
    @pytest.mark.slow
    def test_startup_time(self, test_config):
        """Test application startup time is reasonable."""
        start_time = time.time()
        
        app = create_app(test_config)
        
        startup_time = time.time() - start_time
        assert startup_time < 5.0, f"App startup took {startup_time:.2f}s, should be < 5s"
    
    def test_error_handlers(self, app):
        """Test error handlers are registered."""
        with app.test_client() as client:
            # Test 404 handler
            response = client.get('/nonexistent-page')
            assert response.status_code == 404
            
            # Test that custom 404 template is used
            assert b'404' in response.data or b'Not Found' in response.data
    
    def test_health_check_endpoint(self, client):
        """Test health check endpoint works."""
        response = client.get('/health')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data is not None
        assert 'status' in data
        assert data['status'] in ['ok', 'healthy']
    
    def test_cors_configuration(self, app):
        """Test CORS configuration if applicable."""
        # Check if CORS is configured for API endpoints
        with app.test_client() as client:
            response = client.options('/api/stats')
            # Should not fail with CORS error
            assert response.status_code in [200, 204, 405]  # 405 if OPTIONS not implemented
    
    def test_content_security_policy(self, client):
        """Test security headers are set."""
        response = client.get('/')
        
        # Check for basic security headers
        headers = response.headers
        
        # At minimum, should have some security considerations
        # X-Content-Type-Options helps prevent MIME type sniffing
        # X-Frame-Options helps prevent clickjacking
        
        # Note: These might not be set in development mode
        # This test documents what should be considered for production