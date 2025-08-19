#!/usr/bin/env python3
"""
Demo script showing how to use the VinylVault Discogs client.
This demonstrates the key features and usage patterns.
"""

import logging
from pathlib import Path
from datetime import datetime

from config import Config
from discogs_client import create_discogs_client

# Setup logging for demo
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def demo_basic_usage():
    """Demonstrate basic client usage."""
    print("=== Basic Client Usage Demo ===")
    
    # Create client (without authentication for demo)
    client = create_discogs_client(Config.DATABASE_PATH)
    print(f"✓ Client created, online status: {client.is_online()}")
    
    # Get collection stats (works with local database)
    stats = client.get_collection_stats()
    print(f"📊 Collection stats:")
    print(f"   - Albums: {stats['total_albums']}")
    print(f"   - Artists: {stats['total_artists']}")
    print(f"   - Last sync: {stats['last_sync']['status']}")
    print(f"   - Online: {stats['is_online']}")
    
    # Get sync status
    sync_status = client.get_sync_status()
    print(f"🔄 Sync status: {sync_status['status']}")
    print(f"   - Progress: {sync_status['progress_percent']:.1f}%")
    
    client.close()
    print("✓ Client closed")

def demo_error_handling():
    """Demonstrate error handling patterns."""
    print("\n=== Error Handling Demo ===")
    
    from discogs_client import DiscogsAPIError, DiscogsConnectionError
    
    client = create_discogs_client(Config.DATABASE_PATH)
    
    # Test connection when offline
    success, message = client.test_connection()
    print(f"🔗 Connection test: {'✓' if success else '❌'} {message}")
    
    # Demonstrate search when offline
    try:
        results = client.search_releases("The Beatles")
        print(f"🔍 Search results: {len(results)} found")
    except Exception as e:
        print(f"🔍 Search failed (expected when offline): {type(e).__name__}")
    
    client.close()

def demo_rate_limiting():
    """Demonstrate rate limiting functionality."""
    print("\n=== Rate Limiting Demo ===")
    
    from discogs_client import DiscogsRateLimiter
    import time
    
    # Create a test rate limiter
    limiter = DiscogsRateLimiter(max_requests=3, window=5)
    
    print("Making 5 rapid requests with 3 requests/5 seconds limit...")
    start_time = time.time()
    
    for i in range(5):
        request_start = time.time()
        limiter.wait_if_needed()
        elapsed = time.time() - request_start
        
        total_elapsed = time.time() - start_time
        print(f"Request {i+1}: waited {elapsed:.2f}s (total: {total_elapsed:.2f}s)")
    
    print("✓ Rate limiting demo completed")

def demo_data_structures():
    """Demonstrate data structures and parsing."""
    print("\n=== Data Structures Demo ===")
    
    # Example of what a parsed release looks like
    example_release = {
        'discogs_id': 123456,
        'title': 'Abbey Road',
        'artist': 'The Beatles',
        'year': 1969,
        'genres': ['Rock', 'Pop'],
        'styles': ['Pop Rock', 'Psychedelic Rock'],
        'images': [
            {
                'type': 'primary',
                'uri': 'https://example.com/image.jpg',
                'uri150': 'https://example.com/image_150.jpg',
                'uri600': 'https://example.com/image_600.jpg'
            }
        ],
        'tracklist': [
            {'position': 'A1', 'title': 'Come Together', 'duration': '4:20'},
            {'position': 'A2', 'title': 'Something', 'duration': '3:03'},
        ],
        'notes': 'Excellent condition',
        'rating': 5,
        'date_added': datetime.now().isoformat(),
        'folder_id': 0
    }
    
    print("📀 Example parsed release data:")
    for key, value in example_release.items():
        if isinstance(value, list) and value:
            print(f"   {key}: {len(value)} items")
        else:
            print(f"   {key}: {value}")

def demo_sync_workflow():
    """Demonstrate sync workflow (without actual API calls)."""
    print("\n=== Sync Workflow Demo ===")
    
    client = create_discogs_client(Config.DATABASE_PATH)
    
    # Show what sync status looks like
    status = client.get_sync_status()
    print("🔄 Initial sync status:")
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    # Demonstrate how sync would be started (won't actually start due to offline)
    print("\n📝 Sync workflow steps:")
    print("1. Check if client is online")
    print("2. Test API connection")
    print("3. Get collection info (total items)")
    print("4. Start background sync thread")
    print("5. Fetch collection pages (100 items each)")
    print("6. Process and store each item")
    print("7. Update progress and handle errors")
    print("8. Complete sync and update status")
    
    # Show what a completed sync status might look like
    print("\n✅ Example completed sync status:")
    completed_status = {
        'total_items': 150,
        'processed_items': 150,
        'current_page': 2,
        'total_pages': 2,
        'status': 'completed',
        'start_time': '2024-01-15T10:00:00',
        'estimated_completion': None,
        'progress_percent': 100.0,
        'errors': []
    }
    
    for key, value in completed_status.items():
        print(f"   {key}: {value}")
    
    client.close()

def demo_configuration():
    """Show configuration options."""
    print("\n=== Configuration Demo ===")
    
    print("📋 Current configuration:")
    print(f"   Database path: {Config.DATABASE_PATH}")
    print(f"   Cache directory: {Config.CACHE_DIR}")
    print(f"   Rate limit delay: {Config.RATE_LIMIT_DELAY}s")
    print(f"   User agent: {Config.DISCOGS_USER_AGENT}")
    print(f"   Items per page: {Config.ITEMS_PER_PAGE}")
    print(f"   Max cache size: {Config.MAX_CACHE_SIZE_GB}GB")
    
    # Show additional configuration from our module
    print(f"   Max requests/min: {Config.DISCOGS_MAX_REQUESTS_PER_MINUTE}")
    print(f"   Request timeout: {Config.DISCOGS_REQUEST_TIMEOUT}")
    print(f"   Max retries: {Config.DISCOGS_MAX_RETRIES}")
    print(f"   Sync batch size: {Config.SYNC_BATCH_SIZE}")

def main():
    """Run all demos."""
    print("🎵 VinylVault Discogs Client Demo")
    print("=" * 50)
    print("This demo shows the key features of the Discogs integration.")
    print("Note: Most features require setup and authentication to work fully.\n")
    
    demos = [
        ("Basic Usage", demo_basic_usage),
        ("Error Handling", demo_error_handling),
        ("Rate Limiting", demo_rate_limiting),
        ("Data Structures", demo_data_structures),
        ("Sync Workflow", demo_sync_workflow),
        ("Configuration", demo_configuration),
    ]
    
    for demo_name, demo_func in demos:
        try:
            demo_func()
        except Exception as e:
            print(f"❌ {demo_name} demo failed: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Demo completed!")
    print("\nNext steps:")
    print("1. Run the Flask app: python3 app.py")
    print("2. Complete setup with your Discogs credentials")
    print("3. Use /sync to synchronize your collection")
    print("4. Explore your collection at /")

if __name__ == "__main__":
    main()