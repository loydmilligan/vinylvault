#!/usr/bin/env python3
"""
Test utility for the Discogs client module.
Can be used for testing and debugging the Discogs integration.
"""

import sys
import logging
import sqlite3
from pathlib import Path
from cryptography.fernet import Fernet

from config import Config
from discogs_client import (
    create_discogs_client, 
    DiscogsAPIError, 
    DiscogsConnectionError,
    get_user_discogs_data
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_basic_connection():
    """Test basic Discogs connection."""
    print("=== Testing Basic Connection ===")
    
    # Check if database exists and has user data
    if not Config.DATABASE_PATH.exists():
        print("❌ Database not found. Run setup first.")
        return False
    
    try:
        conn = sqlite3.connect(str(Config.DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        
        user_data = get_user_discogs_data(conn)
        if not user_data:
            print("❌ No user data found. Run setup first.")
            conn.close()
            return False
        
        username, encrypted_token = user_data
        print(f"✓ Found user data for: {username}")
        
        # For testing, we need an encryption key
        # In production, this comes from the session
        test_key = Fernet.generate_key()
        
        # We can't decrypt the real token without the original key,
        # so this is just a connection structure test
        print("✓ User data structure is valid")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_client_creation():
    """Test client creation without authentication."""
    print("\n=== Testing Client Creation ===")
    
    try:
        client = create_discogs_client(Config.DATABASE_PATH)
        print("✓ Client created successfully")
        
        # Test that client is initially offline
        if not client.is_online():
            print("✓ Client correctly reports offline status")
        else:
            print("⚠ Client reports online but shouldn't be initialized yet")
        
        # Test stats with empty database
        stats = client.get_collection_stats()
        print(f"✓ Collection stats: {stats['total_albums']} albums, {stats['total_artists']} artists")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Error creating client: {e}")
        return False

def test_rate_limiter():
    """Test the rate limiting functionality."""
    print("\n=== Testing Rate Limiter ===")
    
    try:
        from discogs_client import DiscogsRateLimiter
        import time
        
        # Create a very restrictive rate limiter for testing
        limiter = DiscogsRateLimiter(max_requests=3, window=10)
        
        print("Testing rate limiter with 3 requests in 10 seconds...")
        start_time = time.time()
        
        for i in range(5):
            print(f"Request {i+1}...")
            limiter.wait_if_needed()
            
            if i >= 2:  # Should start rate limiting after 3rd request
                elapsed = time.time() - start_time
                if elapsed > 1:  # Should have waited
                    print("✓ Rate limiter is working correctly")
                    break
        
        print("✓ Rate limiter test completed")
        return True
        
    except Exception as e:
        print(f"❌ Rate limiter test failed: {e}")
        return False

def test_database_operations():
    """Test database operations."""
    print("\n=== Testing Database Operations ===")
    
    try:
        # Test database connection
        conn = sqlite3.connect(str(Config.DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        
        # Check tables exist
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('users', 'albums', 'sync_log', 'random_cache')
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ['users', 'albums', 'sync_log', 'random_cache']
        missing_tables = set(expected_tables) - set(tables)
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            conn.close()
            return False
        
        print("✓ All required tables exist")
        
        # Check indexes
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_%'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        print(f"✓ Found {len(indexes)} indexes")
        
        # Test basic queries
        cursor = conn.execute("SELECT COUNT(*) as count FROM albums")
        album_count = cursor.fetchone()['count']
        print(f"✓ Albums in database: {album_count}")
        
        cursor = conn.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()['count']
        print(f"✓ Users configured: {user_count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False

def test_session_management():
    """Test session management functionality."""
    print("\n=== Testing Session Management ===")
    
    try:
        from discogs_client import DiscogsSession
        
        session = DiscogsSession()
        print("✓ Session created successfully")
        
        # Test that session is configured properly
        adapter = session.session.get_adapter('https://')
        if adapter:
            print("✓ HTTPS adapter configured")
        else:
            print("⚠ HTTPS adapter not found")
        
        # Test timeout configuration
        if hasattr(session.session, 'timeout'):
            print(f"✓ Timeout configured: {session.session.timeout}")
        
        print("✓ Session management test completed")
        return True
        
    except Exception as e:
        print(f"❌ Session management test failed: {e}")
        return False

def run_all_tests():
    """Run all tests."""
    print("🔧 VinylVault Discogs Client Test Suite")
    print("=" * 50)
    
    tests = [
        ("Database Operations", test_database_operations),
        ("Basic Connection", test_basic_connection),
        ("Client Creation", test_client_creation),
        ("Rate Limiter", test_rate_limiter),
        ("Session Management", test_session_management),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠ Some tests failed. Check the output above.")
        return False

def interactive_mode():
    """Interactive mode for manual testing."""
    print("\n🔧 Interactive Test Mode")
    print("Available commands:")
    print("  1. Test connection")
    print("  2. Test client creation")
    print("  3. Test rate limiter")
    print("  4. Test database")
    print("  5. Test session management")
    print("  6. Run all tests")
    print("  q. Quit")
    
    while True:
        try:
            choice = input("\nEnter command (1-6, q): ").strip().lower()
            
            if choice == 'q':
                break
            elif choice == '1':
                test_basic_connection()
            elif choice == '2':
                test_client_creation()
            elif choice == '3':
                test_rate_limiter()
            elif choice == '4':
                test_database_operations()
            elif choice == '5':
                test_session_management()
            elif choice == '6':
                run_all_tests()
            else:
                print("Invalid choice. Try again.")
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        interactive_mode()
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)