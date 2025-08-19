#!/usr/bin/env python3
"""
Comprehensive diagnosis script for VinylVault setup issues.
This script tests all components that could cause setup failures.
"""

import os
import sys
import json
import tempfile
import requests
from pathlib import Path

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config

def test_environment():
    """Test environment configuration."""
    print("=== Environment Configuration ===")
    issues = []
    
    # Check SECRET_KEY
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key or secret_key == 'dev-secret-key-change-in-production':
        print("⚠️  Using default SECRET_KEY (acceptable for development)")
    else:
        print("✓ SECRET_KEY is configured")
    
    # Check Flask environment
    flask_env = os.environ.get('FLASK_ENV', 'production')
    print(f"✓ FLASK_ENV: {flask_env}")
    
    # Check port
    port = os.environ.get('PORT', '5000')
    print(f"✓ PORT: {port}")
    
    return issues

def test_filesystem_permissions():
    """Test filesystem permissions for cache and database."""
    print("\n=== Filesystem Permissions ===")
    issues = []
    
    # Test cache directory creation
    try:
        Config.CACHE_DIR.mkdir(exist_ok=True)
        print(f"✓ Cache directory accessible: {Config.CACHE_DIR}")
    except Exception as e:
        issues.append(f"Cache directory not writable: {e}")
        print(f"✗ Cache directory error: {e}")
    
    # Test covers directory creation
    try:
        Config.COVERS_DIR.mkdir(exist_ok=True)
        print(f"✓ Covers directory accessible: {Config.COVERS_DIR}")
    except Exception as e:
        issues.append(f"Covers directory not writable: {e}")
        print(f"✗ Covers directory error: {e}")
    
    # Test database file creation
    try:
        # Try to create a test database file
        test_db_path = Config.CACHE_DIR / "test_permissions.db"
        test_db_path.touch()
        test_db_path.unlink()
        print(f"✓ Database directory writable: {Config.DATABASE_PATH.parent}")
    except Exception as e:
        issues.append(f"Database directory not writable: {e}")
        print(f"✗ Database directory error: {e}")
    
    # Test log file creation
    try:
        log_path = Path("test_log.log")
        log_path.touch()
        log_path.unlink()
        print("✓ Log file creation successful")
    except Exception as e:
        issues.append(f"Log file not writable: {e}")
        print(f"✗ Log file error: {e}")
    
    return issues

def test_database_initialization():
    """Test database initialization and operations."""
    print("\n=== Database Initialization ===")
    issues = []
    
    try:
        from init_db import init_database
        import sqlite3
        
        # Initialize database
        init_database()
        print("✓ Database initialization successful")
        
        # Test connection
        conn = sqlite3.connect(str(Config.DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Test table existence
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = ['users', 'albums', 'sync_log', 'random_cache']
        
        for table in expected_tables:
            if table in tables:
                print(f"✓ Table '{table}' exists")
            else:
                issues.append(f"Missing table: {table}")
                print(f"✗ Table '{table}' missing")
        
        # Test basic operations
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"✓ Users table accessible (current count: {user_count})")
        
        conn.close()
        
    except Exception as e:
        issues.append(f"Database initialization failed: {e}")
        print(f"✗ Database error: {e}")
    
    return issues

def test_discogs_api_connectivity():
    """Test basic connectivity to Discogs API."""
    print("\n=== Discogs API Connectivity ===")
    issues = []
    
    try:
        # Test basic HTTP connectivity to Discogs
        response = requests.get("https://api.discogs.com/", timeout=10)
        if response.status_code == 200:
            print("✓ Discogs API endpoint reachable")
        else:
            issues.append(f"Discogs API returned status {response.status_code}")
            print(f"⚠️  Discogs API returned status: {response.status_code}")
        
        # Test user agent requirement
        headers = {"User-Agent": Config.DISCOGS_USER_AGENT}
        response = requests.get("https://api.discogs.com/", headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"✓ User agent accepted: {Config.DISCOGS_USER_AGENT}")
        else:
            issues.append(f"User agent rejected: {response.status_code}")
            print(f"✗ User agent rejected: {response.status_code}")
        
    except requests.exceptions.RequestException as e:
        issues.append(f"Network connectivity to Discogs failed: {e}")
        print(f"✗ Network error: {e}")
    except Exception as e:
        issues.append(f"Discogs connectivity test failed: {e}")
        print(f"✗ Unexpected error: {e}")
    
    return issues

def test_python_dependencies():
    """Test that all required Python dependencies are available."""
    print("\n=== Python Dependencies ===")
    issues = []
    
    required_modules = [
        'flask',
        'discogs_client', 
        'cryptography',
        'requests',
        'sqlite3'
    ]
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError as e:
            issues.append(f"Missing module: {module}")
            print(f"✗ {module}: {e}")
    
    # Test specific imports from the app
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        print("✓ Encryption functionality working")
    except Exception as e:
        issues.append(f"Encryption test failed: {e}")
        print(f"✗ Encryption error: {e}")
    
    return issues

def test_flask_session():
    """Test Flask session functionality."""
    print("\n=== Flask Session Test ===")
    issues = []
    
    try:
        from flask import Flask
        
        # Create a test Flask app
        test_app = Flask(__name__)
        test_app.secret_key = Config.SECRET_KEY
        
        with test_app.test_client() as client:
            with client.session_transaction() as sess:
                sess['test_key'] = 'test_value'
            
            # Test session retrieval
            with client.session_transaction() as sess:
                if sess.get('test_key') == 'test_value':
                    print("✓ Flask sessions working correctly")
                else:
                    issues.append("Flask session data not persisting")
                    print("✗ Flask session data not persisting")
        
    except Exception as e:
        issues.append(f"Flask session test failed: {e}")
        print(f"✗ Flask session error: {e}")
    
    return issues

def main():
    """Run comprehensive diagnostics."""
    print("VinylVault Setup Diagnostics")
    print("=" * 50)
    
    all_issues = []
    
    # Run all diagnostic tests
    test_functions = [
        test_environment,
        test_filesystem_permissions,
        test_database_initialization,
        test_python_dependencies,
        test_flask_session,
        test_discogs_api_connectivity,
    ]
    
    for test_func in test_functions:
        issues = test_func()
        all_issues.extend(issues)
    
    # Summary
    print("\n" + "=" * 50)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 50)
    
    if not all_issues:
        print("🎉 All diagnostic tests passed!")
        print("\nIf setup is still failing, the issue might be:")
        print("1. Invalid Discogs credentials")
        print("2. Empty Discogs collection")
        print("3. Network connectivity issues during setup")
        print("4. Timing issues with Discogs API rate limiting")
        print("\nTry the enhanced setup with detailed logging for more information.")
    else:
        print(f"❌ Found {len(all_issues)} issues:")
        for i, issue in enumerate(all_issues, 1):
            print(f"{i}. {issue}")
        
        print("\nRecommended actions:")
        if any("writable" in issue for issue in all_issues):
            print("- Check Docker volume mounts and file permissions")
        if any("Database" in issue for issue in all_issues):
            print("- Verify database directory is writable")
        if any("Network" in issue or "Discogs" in issue for issue in all_issues):
            print("- Check internet connectivity from container")
        if any("module" in issue for issue in all_issues):
            print("- Reinstall Python dependencies")

if __name__ == "__main__":
    main()