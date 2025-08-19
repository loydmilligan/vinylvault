#!/usr/bin/env python3
"""
Direct setup test script that simulates the exact setup process
without going through the web interface.
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from cryptography.fernet import Fernet
import discogs_client

# Set up detailed logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def generate_encryption_key():
    """Generate encryption key for token storage."""
    return Fernet.generate_key()

def encrypt_token(token: str, key: bytes) -> str:
    """Encrypt user token for secure storage."""
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def get_discogs_client(user_token: str):
    """Get configured Discogs client."""
    return discogs_client.Client(
        Config.DISCOGS_USER_AGENT,
        user_token=user_token
    )

def test_setup_process(username: str, token: str):
    """Test the complete setup process."""
    print(f"Testing setup process for user: {username}")
    print("=" * 50)
    
    # Step 1: Initialize database
    print("\n1. Initializing database...")
    try:
        from init_db import init_database
        
        # Ensure cache directory exists
        Config.CACHE_DIR.mkdir(exist_ok=True)
        print(f"✓ Cache directory: {Config.CACHE_DIR}")
        
        # Initialize database
        init_database()
        print(f"✓ Database initialized: {Config.DATABASE_PATH}")
        
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False
    
    # Step 2: Test database connection
    print("\n2. Testing database connection...")
    try:
        conn = sqlite3.connect(str(Config.DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("SELECT 1")
        print("✓ Database connection successful")
        
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    # Step 3: Test Discogs API
    print("\n3. Testing Discogs API...")
    try:
        client = get_discogs_client(token)
        print(f"✓ Discogs client created with user agent: {Config.DISCOGS_USER_AGENT}")
        
        # Test user access
        print("  Getting user object...")
        user = client.user(username)
        print(f"  ✓ User found: {user.username}")
        
        # Test collection access
        print("  Getting collection folders...")
        collection_folders = user.collection_folders
        print(f"  ✓ Found {len(collection_folders)} collection folders")
        
        if len(collection_folders) == 0:
            print("  ✗ No collection folders found")
            return False
        
        # Test collection access
        print("  Accessing first folder releases...")
        collection = collection_folders[0].releases
        print("  ✓ Collection object created")
        
        # Test getting first item
        print("  Getting first item from collection...")
        try:
            first_release = next(iter(collection))
            print(f"  ✓ First release: {first_release.release.title}")
        except StopIteration:
            print("  ✗ Collection is empty")
            return False
        
    except Exception as e:
        print(f"✗ Discogs API test failed: {e}")
        logger.exception("Discogs API error details:")
        return False
    
    # Step 4: Test encryption
    print("\n4. Testing token encryption...")
    try:
        encryption_key = generate_encryption_key()
        encrypted_token = encrypt_token(token, encryption_key)
        print("✓ Token encryption successful")
        
    except Exception as e:
        print(f"✗ Token encryption failed: {e}")
        return False
    
    # Step 5: Test database insertion
    print("\n5. Testing database insertion...")
    try:
        # Clear any existing test data
        conn.execute("DELETE FROM users WHERE discogs_username = ?", (username,))
        
        # Insert new user data
        conn.execute("""
            INSERT INTO users (discogs_username, user_token)
            VALUES (?, ?)
        """, (username, encrypted_token))
        conn.commit()
        
        # Verify insertion
        cursor = conn.execute("SELECT COUNT(*) as count FROM users WHERE discogs_username = ?", (username,))
        count = cursor.fetchone()['count']
        print(f"✓ User data stored successfully (records: {count})")
        
    except Exception as e:
        print(f"✗ Database insertion failed: {e}")
        return False
    
    # Step 6: Test session simulation (Flask-like)
    print("\n6. Testing session data handling...")
    try:
        # Simulate session storage
        session_data = {
            'encryption_key': encryption_key.decode(),
            'setup_complete': True
        }
        print("✓ Session data prepared")
        
        # Test encryption key decoding
        decoded_key = session_data['encryption_key'].encode()
        if decoded_key == encryption_key:
            print("✓ Encryption key encoding/decoding successful")
        else:
            print("✗ Encryption key encoding/decoding failed")
            return False
        
    except Exception as e:
        print(f"✗ Session simulation failed: {e}")
        return False
    
    # Step 7: Test global client initialization
    print("\n7. Testing Discogs client initialization...")
    try:
        from discogs_client import initialize_global_client
        
        success = initialize_global_client(
            Config.DATABASE_PATH, username, encrypted_token, encryption_key
        )
        
        if success:
            print("✓ Global Discogs client initialized")
        else:
            print("⚠️  Global Discogs client initialization failed (non-critical)")
        
    except Exception as e:
        print(f"⚠️  Global client initialization error: {e} (non-critical)")
    
    # Cleanup
    print("\n8. Cleaning up test data...")
    try:
        conn.execute("DELETE FROM users WHERE discogs_username = ?", (username,))
        conn.commit()
        conn.close()
        print("✓ Test data cleaned up")
        
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 SETUP TEST COMPLETED SUCCESSFULLY!")
    print("\nIf the web setup is still failing after this test passes,")
    print("the issue is likely in the Flask web framework integration,")
    print("session handling, or form processing.")
    
    return True

def main():
    """Main function for interactive testing."""
    print("VinylVault Direct Setup Test")
    print("=" * 50)
    print("This script tests the setup process directly without the web interface.")
    print()
    
    # Get credentials from user
    username = input("Enter your Discogs username: ").strip()
    if not username:
        print("Username is required")
        return
    
    token = input("Enter your Discogs user token: ").strip()
    if not token:
        print("Token is required")
        return
    
    print()
    success = test_setup_process(username, token)
    
    if not success:
        print("\n❌ Setup test failed!")
        print("Check the error messages above for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()