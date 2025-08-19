#!/usr/bin/env python3
"""Debug script to isolate the setup issue."""

import os
import sys
import sqlite3
import logging
from pathlib import Path

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
import discogs_client
from cryptography.fernet import Fernet

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_database_setup():
    """Test database creation and basic operations."""
    print("=== Testing Database Setup ===")
    try:
        # Ensure cache directory exists
        Config.CACHE_DIR.mkdir(exist_ok=True)
        print(f"✓ Cache directory created/exists: {Config.CACHE_DIR}")
        
        # Test database connection
        conn = sqlite3.connect(str(Config.DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Check if users table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone() is not None
        print(f"✓ Users table exists: {table_exists}")
        
        if not table_exists:
            print("Creating users table...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    discogs_username TEXT NOT NULL,
                    user_token TEXT NOT NULL,
                    last_sync TIMESTAMP,
                    total_items INTEGER DEFAULT 0
                );
            """)
            conn.commit()
            print("✓ Users table created")
        
        # Test insertion
        test_data = ('test_user', 'test_token')
        conn.execute("DELETE FROM users WHERE discogs_username = ?", ('test_user',))
        conn.execute("INSERT INTO users (discogs_username, user_token) VALUES (?, ?)", test_data)
        conn.commit()
        
        # Test retrieval
        cursor = conn.execute("SELECT COUNT(*) as count FROM users WHERE discogs_username = ?", ('test_user',))
        count = cursor.fetchone()['count']
        print(f"✓ Database insert/select works: {count} records found")
        
        # Cleanup
        conn.execute("DELETE FROM users WHERE discogs_username = ?", ('test_user',))
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"✗ Database setup failed: {e}")
        logger.exception("Database setup error:")
        return False

def test_encryption():
    """Test token encryption/decryption."""
    print("\n=== Testing Encryption ===")
    try:
        # Generate encryption key
        key = Fernet.generate_key()
        f = Fernet(key)
        
        # Test encryption
        test_token = "test_token_12345"
        encrypted = f.encrypt(test_token.encode()).decode()
        print(f"✓ Token encrypted: {encrypted[:20]}...")
        
        # Test decryption
        decrypted = f.decrypt(encrypted.encode()).decode()
        print(f"✓ Token decrypted: {decrypted}")
        
        if test_token == decrypted:
            print("✓ Encryption/decryption successful")
            return True
        else:
            print("✗ Encryption/decryption mismatch")
            return False
            
    except Exception as e:
        print(f"✗ Encryption test failed: {e}")
        logger.exception("Encryption error:")
        return False

def test_discogs_client_creation():
    """Test basic Discogs client creation."""
    print("\n=== Testing Discogs Client Creation ===")
    try:
        # Test with dummy token
        test_token = "dummy_token"
        client = discogs_client.Client(Config.DISCOGS_USER_AGENT, user_token=test_token)
        print(f"✓ Discogs client created with user agent: {Config.DISCOGS_USER_AGENT}")
        
        # Test user agent format
        if not Config.DISCOGS_USER_AGENT or len(Config.DISCOGS_USER_AGENT) < 5:
            print("✗ Invalid user agent")
            return False
        
        print(f"✓ User agent valid: {Config.DISCOGS_USER_AGENT}")
        return True
        
    except Exception as e:
        print(f"✗ Discogs client creation failed: {e}")
        logger.exception("Discogs client error:")
        return False

def test_discogs_api_with_real_credentials():
    """Test Discogs API with user-provided credentials."""
    print("\n=== Testing Discogs API (Interactive) ===")
    print("This test requires real Discogs credentials.")
    print("If you don't want to test with real credentials, skip this test.")
    
    test_with_real = input("Test with real credentials? (y/N): ").lower().strip()
    if test_with_real != 'y':
        print("Skipping real credentials test")
        return True
    
    username = input("Enter your Discogs username: ").strip()
    token = input("Enter your Discogs user token: ").strip()
    
    if not username or not token:
        print("✗ Username and token required")
        return False
    
    try:
        print(f"Testing connection with username: {username}")
        client = discogs_client.Client(Config.DISCOGS_USER_AGENT, user_token=token)
        
        # Test user access
        print("Getting user object...")
        user = client.user(username)
        print(f"✓ User found: {user.username}")
        
        # Test collection access
        print("Accessing collection folders...")
        folders = user.collection_folders
        print(f"✓ Collection folders: {len(folders)} found")
        
        if len(folders) > 0:
            print("Accessing first folder releases...")
            collection = folders[0].releases
            print(f"✓ Collection object created")
            
            # Test getting first item
            print("Getting first item from collection...")
            try:
                first_item = next(iter(collection))
                print(f"✓ First item retrieved: {first_item.release.title}")
                return True
            except Exception as e:
                print(f"✗ Failed to get first item: {e}")
                logger.exception("Collection iteration error:")
                return False
        else:
            print("✗ No collection folders found")
            return False
            
    except Exception as e:
        print(f"✗ Discogs API test failed: {e}")
        logger.exception("Discogs API error:")
        return False

def main():
    """Run all debug tests."""
    print("VinylVault Setup Debug Tool")
    print("=" * 40)
    
    tests = [
        ("Database Setup", test_database_setup),
        ("Encryption", test_encryption),
        ("Discogs Client Creation", test_discogs_client_creation),
        ("Discogs API (Real Credentials)", test_discogs_api_with_real_credentials),
    ]
    
    results = []
    for test_name, test_func in tests:
        result = test_func()
        results.append((test_name, result))
    
    print("\n" + "=" * 40)
    print("SUMMARY:")
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n🎉 All tests passed! The setup issue might be environment-specific.")
    else:
        print("\n❌ Some tests failed. This might indicate the root cause.")

if __name__ == "__main__":
    main()