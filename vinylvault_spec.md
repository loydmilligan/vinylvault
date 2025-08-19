# VinylVault - One Shot Spec

A touch-optimized record collection browser for Raspberry Pi that provides visual exploration of your Discogs collection with a delightful "spin the crates" random record feature.

## Core Features

* User connects with their Discogs user token (stored locally, never exposed)
* Main screen shows a visual grid of album covers from the user's collection
* Large, prominent vinyl record-shaped button that spins and returns a random album
* Touch-optimized interface designed for 7-inch screens (800x480 minimum)
* Album detail view with cover art, track listing, artist info, and collection notes
* Collection statistics dashboard (total records, genres breakdown, newest additions)
* Infinite scroll or pagination for browsing large collections
* Search and filter by artist, album title, year, or genre
* "Now Playing" mode that displays current album in fullscreen
* Docker containerized for one-command deployment to Raspberry Pi

## Implementation Requirements

* Fetch user's collection from Discogs API on startup and cache locally
* Store album cover images locally after first fetch (respect Discogs rate limits)
* Random record algorithm should weight by play frequency if notes indicate favorites
* Touch gestures: swipe to browse, tap to select, pinch to zoom covers
* Responsive grid that adapts from 2x2 to 4x3 based on screen size
* Background sync every 24 hours to update collection changes
* Graceful offline mode using cached data when internet unavailable
* Maximum 2-second load time for any view using local cache

## Technical Implementation

* Use Python Flask with SQLite database for caching
* Single `app.py` main file with modular templates
* Docker Compose setup with persistent volumes for database and image cache
* Mobile-first responsive design using CSS Grid and Flexbox
* No JavaScript frameworks - vanilla JS for interactions
* Touch events handled natively, no complex gesture libraries
* python3-discogs-client for API integration
* Pillow for image optimization and caching

## File Structure
```
vinylvault/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container configuration
├── docker-compose.yml    # Orchestration with volumes
├── config.py            # Configuration and settings
├── templates/
│   ├── index.html       # Main collection grid
│   ├── album.html       # Album detail view
│   └── setup.html       # Initial token setup
├── static/
│   ├── style.css        # All styles, mobile-first
│   ├── app.js          # Minimal interactions
│   └── vinyl-icon.svg  # Random button graphic
└── cache/
    ├── vinylvault.db    # SQLite for collection data
    └── covers/          # Cached album artwork
```

## Database Schema

```sql
-- Users table (single user for Pi deployment)
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    discogs_username TEXT,
    user_token TEXT,
    last_sync TIMESTAMP,
    total_items INTEGER
);

-- Albums cache
CREATE TABLE albums (
    id INTEGER PRIMARY KEY,
    discogs_id INTEGER UNIQUE,
    title TEXT,
    artist TEXT,
    year INTEGER,
    cover_url TEXT,
    cover_cached BOOLEAN DEFAULT 0,
    genres TEXT,  -- JSON array
    styles TEXT,  -- JSON array
    tracklist TEXT,  -- JSON
    notes TEXT,
    rating INTEGER,
    date_added TIMESTAMP,
    folder_id INTEGER,
    play_count INTEGER DEFAULT 0,
    last_played TIMESTAMP
);

-- Sync status
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY,
    sync_time TIMESTAMP,
    items_synced INTEGER,
    status TEXT
);
```

## UI/UX Requirements

* **Touch-first design**: 44px minimum touch targets, generous spacing
* **Visual hierarchy**: Album covers are the hero, text is secondary
* **Random button**: Animated vinyl record that spins when touched, 150px diameter
* **Grid layout**: Responsive 2-4 columns, square album covers with lazy loading
* **Color scheme**: Dark theme by default (OLED friendly), optional light mode
* **Typography**: System fonts for speed, high contrast for readability
* **Loading states**: Skeleton screens while images load, no jarring layouts
* **Smooth animations**: CSS transforms only, 60fps on Pi hardware
* **Gesture support**: Swipe between albums, pull-to-refresh collection

## Docker Deployment

```yaml
# docker-compose.yml structure
version: '3.8'
services:
  vinylvault:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./cache:/app/cache
    environment:
      - FLASK_ENV=production
    restart: unless-stopped
```

## API Integration Details

* Use Discogs user token authentication (simpler than OAuth)
* Respect rate limits: 60 requests per minute maximum
* Batch fetch collection in pages of 100 items
* Cache everything aggressively to minimize API calls
* Only fetch images on-demand, store permanently
* Use collection folders to organize if user has them
* Handle API errors gracefully with exponential backoff

## Success Criteria

* Loads user's collection within 5 seconds on first run
* Random record feature responds instantly using cached data
* Touch interactions feel native and responsive
* Works offline after initial sync
* One-command deployment via docker-compose
* Runs smoothly on Raspberry Pi 5 with 60fps scrolling
* Images are optimized for 7-inch screen resolution

## Performance Optimizations

* Pre-calculate random selections for instant response
* Lazy load images with intersection observer
* Use WebP format for cached covers if supported
* Index database on commonly searched fields
* Implement virtual scrolling for collections over 500 items
* Progressive web app capabilities for app-like experience

## Claude Code Integration Note

This project has access to specialized Claude Code subagents (code-reviewer, debugger, etc.) and can follow the 4-phase workflow outlined above. The Docker setup ensures consistent development between laptop and Raspberry Pi deployment.

## Constraints

* Maximum 1000 lines of code across all files
* No complex build processes or transpilation
* Must work on Raspberry Pi 5 with Raspbian out of the box
* Single Docker container, no orchestration complexity
* Avoid memory-heavy operations that could crash Pi
* Touch-first, mouse/keyboard secondary
* Offline-first after initial setup

## MVP Constraints

* Single user only (personal Pi deployment)
* English language only
* No social features or sharing
* Basic search only (no complex queries)
* No playlist or queue management
* No audio playback integration
* Read-only Discogs integration (no collection updates)
* No backup/restore features initially

---

## Implementation Prompt

```
Review the vinylvault_spec.md file in detail. Follow the 4-phase workflow (Research → Design → Frontend → Backend) to implement a working prototype.

Focus on:
- Building a Flask web app optimized for Raspberry Pi touch screen
- Docker containerization for easy deployment
- Touch-first UI with the signature random record button
- Efficient Discogs API usage with aggressive caching
- Beautiful visual browsing of record collection

Phase 1: Research Discogs API authentication and collection endpoints
Phase 2: Design touch-optimized UI mockups for 800x480 screen
Phase 3: Build Flask routes and responsive templates
Phase 4: Implement Discogs integration and Docker setup

Use python3-discogs-client for API integration. Ensure the random record button is delightful - it should spin like a real record when touched. Ship a working prototype that runs with `docker-compose up`.
```

## Key Implementation Notes

### 1. Discogs Token Setup
First run shows setup screen where user enters their Discogs username and personal access token. These are stored encrypted in the SQLite database.

### 2. Random Record Algorithm
- Pre-generate 10 random selections on each sync
- Weight by rating if available (5-star gets 5x weight)
- Never repeat within last 20 selections
- Spin animation takes 2 seconds, result appears as it slows

### 3. Image Caching Strategy
- Fetch 150px thumbnails for grid view
- Fetch 600px versions only when album is viewed
- Convert to WebP with 85% quality to save space
- Limit cache to 2GB, LRU eviction policy

### 4. Touch Optimizations
- Disable double-tap zoom
- Fast-tap detection (no 300ms delay)
- Momentum scrolling on collection grid
- Swipe gestures for album detail navigation

### 5. Docker Considerations
- Multi-stage build to minimize image size
- Health check endpoint for container monitoring
- Graceful shutdown handling to prevent database corruption
- Volume mapping for persistent storage across updates

## Additional Implementation Details

### Flask Routes

```python
# Core routes structure
/                    # Main collection grid
/setup              # Initial configuration
/album/<id>         # Album detail view
/random             # Random album endpoint
/search             # Search results
/stats              # Collection statistics
/sync               # Manual sync trigger
/api/collection     # JSON endpoint for JS
/api/album/<id>     # Album data endpoint
/health             # Docker health check
```

### Caching Strategy

1. **Initial Sync**: Fetch all collection items, store metadata
2. **Image Loading**: Lazy load on viewport entry
3. **Cache Warming**: Pre-fetch next page of results
4. **Offline Mode**: Service worker for PWA functionality
5. **Update Strategy**: Delta sync for changes only

### Error Handling

- Network failures: Fall back to cached data
- API rate limits: Exponential backoff with user notification
- Missing images: Display vinyl record placeholder
- Database locks: Retry with timeout
- Docker issues: Automatic restart policy

### Security Considerations

- User token encrypted with Fernet (cryptography library)
- No external network access except Discogs API
- Input sanitization for search queries
- Rate limiting on local API endpoints
- CORS disabled (local use only)

This spec provides everything needed to build a delightful, touch-optimized record collection browser that will work beautifully on your Raspberry Pi setup while being developed on your laptop.