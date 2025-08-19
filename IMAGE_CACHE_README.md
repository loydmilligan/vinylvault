# VinylVault Image Cache System

A comprehensive image caching system designed for VinylVault with WebP optimization, multi-size caching, LRU eviction, and Raspberry Pi optimization.

## Features

### Core Features
- **WebP Optimization**: Converts images to WebP format with 85% quality for optimal file sizes
- **Multi-Size Caching**: 150px thumbnails for grid view, 600px for detail view
- **LRU Eviction**: Maintains 2GB cache limit with least-recently-used eviction
- **Lazy Loading**: On-demand image fetching with placeholder support
- **Background Processing**: Non-blocking image downloads and processing
- **Error Handling**: Graceful fallback for missing/corrupt images

### Raspberry Pi Optimizations
- **Memory Efficient**: Optimized image processing to prevent memory issues
- **Thread-Safe**: Concurrent access support with proper locking
- **Connection Pooling**: Efficient HTTP requests with retry logic
- **Garbage Collection**: Proactive memory cleanup during processing

### Integration Features
- **Flask Integration**: Template helpers and route handlers
- **Database Metadata**: SQLite storage for cache metadata
- **Progress Tracking**: Monitoring for batch downloads
- **Cache Statistics**: Performance metrics and monitoring
- **API Endpoints**: RESTful cache management

## Installation and Setup

### 1. Dependencies
The image cache system requires the following Python packages (already in requirements.txt):
```
Pillow==10.2.0
requests==2.31.0
```

### 2. Automatic Initialization
The cache system is automatically initialized when the Flask app starts:
```python
# In app.py - automatically called
initialize_image_cache_if_needed()
```

### 3. Manual Initialization
For standalone use:
```python
from image_cache import initialize_image_cache, get_image_cache
from pathlib import Path

# Initialize cache
cache_dir = Path("cache/covers")
database_path = Path("cache/vinylvault.db")
success = initialize_image_cache(cache_dir, database_path)

# Get cache instance
cache = get_image_cache()
```

## Usage

### Template Integration
The system provides template helpers for easy integration:

```html
<!-- For thumbnail images (150px) -->
<img data-src="{{ get_thumbnail_url(album.cover_url) }}" 
     data-original-src="{{ album.cover_url }}"
     data-size-type="thumbnails"
     alt="{{ album.title }}" 
     class="lazy-load"
     loading="lazy">

<!-- For detail images (600px) -->
<img data-src="{{ get_detail_image_url(album.cover_url) }}" 
     data-original-src="{{ album.cover_url }}"
     data-size-type="detail"
     src="{{ get_placeholder_url('detail') }}"
     alt="{{ album.title }}"
     class="lazy-load"
     loading="lazy">

<!-- Placeholder fallback -->
<img src="{{ get_placeholder_url('thumbnails') }}" 
     alt="{{ album.title }}"
     class="placeholder">
```

### JavaScript Integration
Enhanced lazy loading with cache awareness:

```javascript
// Preload images for current page
VinylVault.preloadCurrentPageImages();

// Get cache statistics
const stats = await VinylVault.getCacheStats();

// Clear image cache
const success = await VinylVault.clearImageCache();
```

### Python API
Direct cache operations:

```python
cache = get_image_cache()

# Get cached image path
cached_path = cache.get_image(discogs_url, 'thumbnails')

# Preload multiple images
urls = ['url1', 'url2', 'url3']
results = cache.preload_images(urls)

# Get cache statistics
stats = cache.get_cache_stats()

# Cleanup old entries
cleaned = cache.cleanup_cache(max_age_days=30)
```

## API Endpoints

### Cache Statistics
```
GET /api/cache/stats
```
Returns comprehensive cache statistics including hit rate, size, and performance metrics.

### Cache Management
```
POST /api/cache/clear
```
Clears all cached images.

```
POST /api/cache/preload
Content-Type: application/json
{
  "urls": ["url1", "url2", "url3"]
}
```
Preloads images in background.

### Image Serving
```
GET /cache/thumbnails/{hash}.webp
GET /cache/detail/{hash}.webp
GET /cache/placeholders/placeholder_{type}.webp
```
Serves cached images with proper caching headers.

## Monitoring and Management

### Cache Monitor Script
Use the included monitoring script for cache management:

```bash
# Check cache status
python cache_monitor.py --action status

# Get health check
python cache_monitor.py --action health

# Clean up old entries
python cache_monitor.py --action cleanup --cleanup-days 30

# Generate performance report
python cache_monitor.py --action report

# Continuous monitoring
python cache_monitor.py --action monitor --monitor-interval 300
```

### Cache Statistics
Monitor cache performance:
- **Hit Rate**: Percentage of requests served from cache
- **Total Entries**: Number of cached images
- **Cache Size**: Total storage used
- **Memory Usage**: RAM utilization
- **Eviction Count**: Number of LRU evictions

## Configuration

### Cache Settings (config.py)
```python
# Cache directories
CACHE_DIR = BASE_DIR / 'cache'
COVERS_DIR = CACHE_DIR / 'covers'

# Cache limits
MAX_CACHE_SIZE_GB = 2

# Image settings
THUMBNAIL_SIZE = 150
DETAIL_SIZE = 600
IMAGE_QUALITY = 85

# Performance settings
MAX_CONCURRENT_DOWNLOADS = 3
MEMORY_CACHE_SIZE_MB = 128
```

### Environment Variables
```bash
# Optional: Override cache size
VINYL_VAULT_CACHE_SIZE_GB=2

# Optional: Enable debug logging
VINYL_VAULT_DEBUG=1
```

## Performance Optimization

### Raspberry Pi Specific
- **Memory Management**: Proactive garbage collection
- **CPU Optimization**: Efficient image processing algorithms
- **I/O Optimization**: Asynchronous file operations
- **Network Optimization**: Connection pooling and retry logic

### Browser Optimization
- **Lazy Loading**: Only load visible images
- **WebP Support**: Modern format for better compression
- **Progressive Enhancement**: Fallback for older browsers
- **Preloading**: Background loading of likely-needed images

## Troubleshooting

### Common Issues

1. **Cache Not Initializing**
   ```bash
   # Check permissions
   ls -la cache/
   
   # Check disk space
   df -h
   
   # Check logs
   tail -f vinylvault.log
   ```

2. **Images Not Loading**
   ```bash
   # Test cache functionality
   python test_image_cache.py
   
   # Check cache stats
   python cache_monitor.py --action health
   ```

3. **Performance Issues**
   ```bash
   # Monitor cache performance
   python cache_monitor.py --action monitor
   
   # Clear cache if needed
   curl -X POST http://localhost:5000/api/cache/clear
   ```

### Debug Mode
Enable debug logging:
```python
import logging
logging.getLogger('image_cache').setLevel(logging.DEBUG)
```

## File Structure

```
vinylvault/
├── image_cache.py              # Main cache implementation
├── cache_monitor.py            # Monitoring and management
├── test_image_cache.py         # Test suite
├── app.py                      # Flask integration
├── static/
│   ├── app.js                  # Enhanced with cache features
│   └── style.css               # Cache-specific styles
├── templates/
│   ├── index.html              # Updated with cache helpers
│   └── album_detail.html       # Updated with cache helpers
└── cache/
    └── covers/
        ├── thumbnails/         # 150px cached images
        ├── detail/             # 600px cached images
        └── placeholders/       # Generated placeholders
```

## Testing

Run the test suite to verify functionality:
```bash
python test_image_cache.py
```

The test suite covers:
- Basic cache operations
- Image processing
- LRU eviction
- Performance metrics
- Memory optimization
- Error handling

## Security Considerations

- **Input Validation**: All URLs are validated before processing
- **Path Traversal**: Cache paths are restricted to cache directory
- **Rate Limiting**: API endpoints include rate limiting
- **Content Type Validation**: Only image content is processed
- **Size Limits**: Maximum image size restrictions

## Future Enhancements

- **CDN Integration**: Optional CDN support for distributed caching
- **Image Variants**: Additional sizes for different use cases
- **Smart Preloading**: AI-driven preloading based on user behavior
- **Compression Levels**: Adaptive quality based on connection speed
- **Backup/Restore**: Cache backup and restoration utilities

## License

This image cache system is part of VinylVault and follows the same license terms.