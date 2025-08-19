# VinylVault Discogs Integration

This document explains the comprehensive Discogs API integration in VinylVault, including features, usage, and configuration.

## Overview

The VinylVault Discogs integration provides a robust, production-ready interface to the Discogs API with the following key features:

- **Secure Authentication**: Encrypted token storage with Fernet encryption
- **Rate Limiting**: Respects Discogs' 60 requests/minute limit with intelligent throttling
- **Background Sync**: Non-blocking collection synchronization with progress tracking
- **Error Handling**: Comprehensive error handling with retry logic and exponential backoff
- **Offline Support**: Graceful degradation when API is unavailable
- **Performance Optimized**: Connection pooling, caching, and Raspberry Pi optimizations
- **Real-time Progress**: Live sync status updates with ETA calculations

## Core Components

### 1. DiscogsClient (`discogs_client.py`)

Main client class that handles all Discogs interactions:

```python
from discogs_client import create_discogs_client

# Create client
client = create_discogs_client(database_path)

# Initialize with credentials
success = client.initialize(username, encrypted_token, encryption_key)

# Test connection
online, message = client.test_connection()

# Start background sync
client.sync_collection(background=True)

# Get sync status
status = client.get_sync_status()

# Get collection statistics
stats = client.get_collection_stats()
```

### 2. Rate Limiting

Intelligent rate limiting prevents API abuse:

```python
from discogs_client import DiscogsRateLimiter

limiter = DiscogsRateLimiter(max_requests=55, window=60)
limiter.wait_if_needed()  # Blocks if rate limit would be exceeded
```

### 3. Session Management

Enhanced HTTP session with connection pooling and retries:

```python
from discogs_client import DiscogsSession

session = DiscogsSession()
response = session.get(url)  # Automatic retries on failure
```

### 4. Background Synchronization

Non-blocking sync with progress tracking:

```python
# Start background sync
client.sync_collection(background=True, force_full=False)

# Monitor progress
status = client.get_sync_status()
print(f"Progress: {status['progress_percent']:.1f}%")
print(f"Status: {status['status']}")
print(f"ETA: {status['estimated_completion']}")

# Cancel if needed
client.cancel_sync()
```

## Flask Integration

### Setup and Initialization

The Flask app automatically initializes the Discogs client during setup:

```python
# app.py automatically handles:
# 1. Client creation
# 2. Credential management
# 3. Session integration
# 4. Global client instance
```

### API Endpoints

New API endpoints for Discogs integration:

#### GET `/api/sync/status`
Get current sync status and collection statistics:

```json
{
  "sync_status": {
    "status": "syncing",
    "progress_percent": 45.2,
    "processed_items": 68,
    "total_items": 150,
    "estimated_completion": "2024-01-15T10:15:30"
  },
  "collection_stats": {
    "total_albums": 68,
    "total_artists": 45,
    "last_sync": {
      "time": "2024-01-15T10:00:00",
      "status": "in_progress"
    }
  },
  "client_online": true
}
```

#### POST `/api/sync/start`
Start collection synchronization:

```bash
curl -X POST http://localhost:5000/api/sync/start \
  -H "Content-Type: application/json" \
  -d '{"force_full": false}'
```

#### POST `/api/sync/cancel`
Cancel ongoing synchronization:

```bash
curl -X POST http://localhost:5000/api/sync/cancel
```

#### GET `/api/search?q=query&limit=10`
Search Discogs releases (requires online connection):

```json
{
  "query": "The Beatles",
  "results": [
    {
      "id": 123456,
      "title": "Abbey Road",
      "artist": "The Beatles",
      "year": 1969,
      "format": ["Vinyl", "LP"],
      "thumb": "https://example.com/thumb.jpg"
    }
  ],
  "count": 1
}
```

### Enhanced Sync Route

The `/sync` route now provides comprehensive sync management:

- Real-time sync status display
- Progress tracking with percentage and ETA
- Error reporting and recovery
- Force full sync option
- Cancel sync capability

## Configuration

Enhanced configuration options in `config.py`:

```python
# Discogs API settings
DISCOGS_USER_AGENT = 'VinylVault/1.0'
DISCOGS_MAX_REQUESTS_PER_MINUTE = 55  # Conservative limit
DISCOGS_REQUEST_TIMEOUT = (10, 30)    # (connect, read) timeouts
DISCOGS_MAX_RETRIES = 3
DISCOGS_RETRY_DELAY = 1.0

# Sync settings
SYNC_BATCH_SIZE = 100                 # Items per batch
SYNC_PROGRESS_LOG_INTERVAL = 50       # Log every N items
SYNC_MAX_ERRORS = 10                  # Stop sync after N errors

# Performance settings for Raspberry Pi
MAX_CONCURRENT_DOWNLOADS = 3
MEMORY_CACHE_SIZE_MB = 128
DATABASE_WAL_MODE = True
```

## Data Processing

### Release Data Extraction

The client extracts comprehensive metadata from Discogs releases:

```python
{
    'discogs_id': 123456,
    'title': 'Album Title',
    'artist': 'Artist Name',
    'year': 1970,
    'genres': ['Rock', 'Pop'],
    'styles': ['Psychedelic', 'Blues Rock'],
    'images': [
        {
            'type': 'primary',
            'uri': 'full_size_image_url',
            'uri150': 'thumbnail_url',
            'uri600': 'medium_size_url'
        }
    ],
    'tracklist': [
        {
            'position': 'A1',
            'title': 'Track Name',
            'duration': '4:20'
        }
    ],
    'notes': 'User notes',
    'rating': 5,
    'date_added': '2024-01-15T10:00:00',
    'folder_id': 0
}
```

### Database Storage

Data is stored efficiently in SQLite with proper indexing:

- JSON fields for complex data (genres, tracklist)
- Proper foreign key relationships
- Optimized indexes for search and sorting
- WAL mode for better concurrency

## Error Handling

Comprehensive error handling with specific exception types:

```python
from discogs_client import (
    DiscogsAPIError,
    DiscogsRateLimitError,
    DiscogsAuthenticationError,
    DiscogsConnectionError
)

try:
    client.sync_collection()
except DiscogsRateLimitError:
    # Rate limit exceeded - handled automatically
    pass
except DiscogsAuthenticationError:
    # Invalid credentials
    pass
except DiscogsConnectionError:
    # Network issues
    pass
except DiscogsAPIError:
    # General API errors
    pass
```

### Retry Logic

Automatic retries with exponential backoff:

```python
@retry_on_failure(max_retries=3, delay=1.0)
def api_operation():
    # Will retry up to 3 times with exponential backoff
    pass
```

## Performance Optimizations

### Raspberry Pi Specific

- Conservative rate limiting (55/minute instead of 60)
- Connection pooling to reduce overhead
- Efficient memory usage with streaming
- Background processing to avoid blocking UI
- WAL mode for database concurrency

### Caching

- LRU cache for frequently accessed data
- Image URL caching
- Collection info caching
- Session reuse for HTTP connections

### Database Optimizations

- Proper indexing for fast queries
- Batch inserts for efficiency
- Foreign key constraints for data integrity
- JSON storage for complex fields

## Testing and Debugging

### Test Suite

Run the comprehensive test suite:

```bash
python3 test_discogs.py
```

Available tests:
- Database operations
- Client creation and initialization
- Rate limiting functionality
- Session management
- Error handling

### Interactive Testing

```bash
python3 test_discogs.py --interactive
```

### Demo Script

See the integration in action:

```bash
python3 demo_discogs_usage.py
```

## Security

### Token Encryption

User tokens are encrypted using Fernet symmetric encryption:

```python
from cryptography.fernet import Fernet

# Generate key
key = Fernet.generate_key()

# Encrypt token
f = Fernet(key)
encrypted_token = f.encrypt(token.encode())

# Store encrypted token in database
# Store key in session (for this deployment model)
```

### Secure Session Management

- HTTPS-only session configuration
- Proper timeout handling
- Secure headers for all responses
- Input validation and sanitization

## Monitoring and Logging

### Comprehensive Logging

```python
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discogs_client')

# Log levels used:
# DEBUG: Detailed operation info
# INFO: General operation status
# WARNING: Recoverable issues
# ERROR: Serious problems
```

### Sync Progress Tracking

Real-time progress updates during sync:

- Items processed vs total
- Current page and total pages
- Estimated completion time
- Error count and details
- Processing rate (items/second)

## Common Usage Patterns

### Initial Setup

1. User provides Discogs username and token
2. System tests API connection
3. Token is encrypted and stored
4. Global client is initialized
5. Ready for synchronization

### Regular Sync

1. User triggers sync via web UI or API
2. System checks connection and rate limits
3. Background sync starts with progress tracking
4. Real-time updates via status API
5. Completion notification

### Error Recovery

1. Automatic retries for transient errors
2. Exponential backoff for rate limits
3. Graceful degradation for network issues
4. Detailed error logging for debugging
5. User notifications for persistent issues

## Deployment Considerations

### Raspberry Pi Deployment

- Conservative resource usage
- Efficient database operations
- Background processing
- Automatic error recovery
- Minimal memory footprint

### Docker Integration

The client is fully compatible with Docker deployment:

```dockerfile
# Already configured in existing Dockerfile
RUN pip install -r requirements.txt
```

### Environment Variables

Optional environment variables for configuration:

```bash
DISCOGS_RATE_LIMIT=50          # Custom rate limit
DISCOGS_TIMEOUT=30             # Request timeout
DISCOGS_MAX_RETRIES=5          # Retry attempts
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify username and token
   - Check token permissions
   - Ensure proper encryption key

2. **Rate Limiting**
   - Client automatically handles this
   - Check logs for rate limit messages
   - Reduce concurrent operations if needed

3. **Connection Issues**
   - Check internet connectivity
   - Verify Discogs API status
   - Check firewall/proxy settings

4. **Sync Failures**
   - Check detailed error logs
   - Verify database permissions
   - Ensure sufficient disk space

### Debug Mode

Enable detailed logging for troubleshooting:

```python
import logging
logging.getLogger('discogs_client').setLevel(logging.DEBUG)
```

### Health Checks

Use the health endpoint to verify system status:

```bash
curl http://localhost:5000/health
```

## Future Enhancements

Potential improvements for future versions:

- Image caching and processing
- Incremental sync (only new/changed items)
- Multiple user support
- Advanced search and filtering
- Collection value tracking
- Backup and restore functionality
- Export to other formats
- Social features (sharing, recommendations)

## Support

For issues and questions:

1. Check the test suite output
2. Review application logs
3. Verify configuration settings
4. Test with demo script
5. Check Discogs API documentation

## Conclusion

The VinylVault Discogs integration provides a robust, production-ready solution for managing vinyl collections with the Discogs API. It's designed specifically for Raspberry Pi deployment while maintaining professional-grade reliability and performance.

The modular design allows for easy testing, debugging, and future enhancements while providing a seamless user experience through the Flask web interface.