#!/usr/bin/env python3
"""
VinylVault - Personal Vinyl Collection Manager
Main Flask application
"""

import os
import json
import sqlite3
import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from typing import Optional, Dict, List, Any
from dataclasses import asdict

from flask import (
    Flask, render_template, request, jsonify, redirect, url_for, 
    session, flash, abort, g, make_response, send_file, send_from_directory
)
from werkzeug.exceptions import NotFound, InternalServerError
from cryptography.fernet import Fernet

from config import Config
from discogs_custom_client import (
    initialize_global_client, initialize_global_client_simple, get_global_client, shutdown_global_client,
    get_user_discogs_data, DiscogsAPIError, DiscogsConnectionError
)

# Import the actual discogs_client library (now that local file is renamed)
import discogs_client
from image_cache import (
    initialize_image_cache, get_image_cache, shutdown_image_cache,
    get_cached_image_url, get_placeholder_url
)
from random_algorithm import (
    initialize_random_algorithm, get_random_album, record_album_feedback,
    get_algorithm_statistics, refresh_algorithm_cache, AlgorithmConfig
)
from ab_testing import (
    get_ab_manager, get_user_algorithm_config, record_selection_metric, 
    record_feedback_metric, create_rating_weight_test, create_diversity_weight_test
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vinylvault.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# Initialize image cache
def initialize_image_cache_if_needed():
    """Initialize image cache if needed."""
    try:
        cache = get_image_cache()
        if cache is not None:
            return
            
        cache_dir = Config.CACHE_DIR / 'covers'
        success = initialize_image_cache(
            cache_dir, 
            Config.DATABASE_PATH, 
            max_cache_size=2 * 1024 * 1024 * 1024  # 2GB
        )
        if success:
            logger.info("Image cache initialized successfully")
        else:
            logger.warning("Failed to initialize image cache")
    except Exception as e:
        logger.error(f"Error initializing image cache: {e}")

# Initialize random algorithm
def initialize_random_algorithm_if_needed():
    """Initialize random algorithm if needed."""
    try:
        success = initialize_random_algorithm(str(Config.DATABASE_PATH))
        if success:
            logger.info("Random algorithm initialized successfully")
        else:
            logger.warning("Failed to initialize random algorithm")
    except Exception as e:
        logger.error(f"Error initializing random algorithm: {e}")

# Initialize global Discogs client
def initialize_discogs_if_needed():
    """Initialize Discogs client if needed."""
    try:
        # Only initialize if we have a global client not set up yet
        client = get_global_client()
        if client is not None:
            return
            
        # Use environment variables directly
        import os
        username = os.environ.get('DISCOGS_USERNAME')
        token = os.environ.get('DISCOGS_TOKEN')
        
        if username and token:
            # Initialize directly without encryption
            success = initialize_global_client_simple(
                Config.DATABASE_PATH, username, token
            )
            if success:
                logger.info("Discogs client initialized successfully")
            else:
                logger.warning("Failed to initialize Discogs client")
        else:
            logger.warning("Discogs credentials not found in environment variables")
    except Exception as e:
        logger.error(f"Error initializing Discogs client: {e}")

# Cleanup on app shutdown
@app.teardown_appcontext
def cleanup_discogs(error):
    """Cleanup resources on app context teardown."""
    # Note: Global client cleanup happens on app shutdown, not per request
    pass

from atexit import register
register(shutdown_global_client)
register(shutdown_image_cache)

# Rate limiting storage (simple in-memory for single-user Pi deployment)
rate_limit_storage = {}

def generate_encryption_key():
    """Get encryption key from environment variable."""
    import os
    
    encryption_key = os.environ.get('ENCRYPTION_KEY')
    if not encryption_key:
        raise ValueError("ENCRYPTION_KEY environment variable not set")
    
    return encryption_key.encode('utf-8')

def encrypt_token(token: str, key: bytes) -> str:
    """Encrypt user token for secure storage."""
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str, key: bytes) -> str:
    """Decrypt user token."""
    f = Fernet(key)
    return f.decrypt(encrypted_token.encode()).decode()

def get_db():
    """Get database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(str(Config.DATABASE_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(error):
    """Close database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.teardown_appcontext
def close_db_teardown(error):
    """Close database connection on teardown."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def rate_limit(max_requests: int = 60, window: int = 60):
    """Simple rate limiting decorator."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            now = datetime.now()
            
            # Clean old entries
            cutoff = now - timedelta(seconds=window)
            if client_ip in rate_limit_storage:
                rate_limit_storage[client_ip] = [
                    req_time for req_time in rate_limit_storage[client_ip] 
                    if req_time > cutoff
                ]
            
            # Check rate limit
            if client_ip not in rate_limit_storage:
                rate_limit_storage[client_ip] = []
            
            if len(rate_limit_storage[client_ip]) >= max_requests:
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            rate_limit_storage[client_ip].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def is_setup_complete():
    """Check if initial setup is complete."""
    try:
        db = get_db()
        cursor = db.execute("SELECT COUNT(*) as count FROM users")
        result = cursor.fetchone()
        return result['count'] > 0
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return False

def get_user_data():
    """Get user configuration data."""
    try:
        db = get_db()
        cursor = db.execute("SELECT * FROM users LIMIT 1")
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting user data: {e}")
        return None

def get_discogs_client(user_token: str):
    """Get configured Discogs client."""
    return discogs_client.Client(
        Config.DISCOGS_USER_AGENT,
        user_token=user_token
    )

def mobile_optimized_response(response):
    """Add mobile optimization headers."""
    response.headers['Cache-Control'] = 'public, max-age=300'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.before_request
def before_request():
    """Pre-request setup."""
    # Skip setup check for static files and health check
    if request.endpoint in ['static', 'health']:
        return
    
    # Ensure database is initialized before any operations
    if not Config.DATABASE_PATH.exists():
        logger.warning("Database not found, initializing...")
        try:
            from init_db import init_database
            init_database()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Continue anyway, let the actual DB operations fail with proper errors
    
    # Check if setup is required
    if not is_setup_complete() and request.endpoint != 'setup':
        return redirect(url_for('setup'))
    
    # Initialize Discogs client, image cache, and random algorithm if needed
    if is_setup_complete():
        initialize_discogs_if_needed()
        initialize_image_cache_if_needed()
        initialize_random_algorithm_if_needed()

# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal error: {error}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

# Routes
@app.route('/health')
def health():
    """Docker health check endpoint."""
    try:
        # Check database connectivity
        db = get_db()
        db.execute("SELECT 1")
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Initial setup route."""
    if request.method == 'GET':
        return render_template('setup.html')
    
    try:
        username = request.form.get('username', '').strip()
        token = request.form.get('token', '').strip()
        
        if not username or not token:
            logger.warning("Setup attempted with missing username or token")
            flash('Username and token are required', 'error')
            return render_template('setup.html')
        
        logger.info(f"Starting setup for user: {username}")
        
        # Test database connection first
        try:
            db = get_db()
            db.execute("SELECT 1")
            logger.info("Database connection test successful")
        except Exception as db_error:
            logger.error(f"Database connection failed: {db_error}")
            flash('Database connection error. Please check system configuration.', 'error')
            return render_template('setup.html')
        
        # Test Discogs connection
        logger.info("Testing Discogs API connection...")
        client = get_discogs_client(token)
        try:
            user = client.user(username)
            logger.info(f"Discogs user object retrieved for: {user.username}")
            
            collection_folders = user.collection_folders
            logger.info(f"Found {len(collection_folders)} collection folders")
            
            if not collection_folders:
                logger.error("No collection folders found for user")
                flash('No collection found for this user. Please check your username.', 'error')
                return render_template('setup.html')
            
            collection = collection_folders[0].releases
            logger.info("Attempting to access collection releases...")
            
            # Test API access by getting first item
            first_release = next(iter(collection))
            logger.info(f"Successfully accessed collection. First release: {first_release.release.title}")
            
        except StopIteration:
            logger.error("Collection is empty")
            flash('Your collection appears to be empty. Please add some records to your Discogs collection first.', 'error')
            return render_template('setup.html')
        except Exception as api_error:
            logger.error(f"Discogs API test failed: {api_error}")
            logger.error(f"Error type: {type(api_error).__name__}")
            if "401" in str(api_error) or "Unauthorized" in str(api_error):
                flash('Invalid token. Please check your Discogs user token.', 'error')
            elif "404" in str(api_error) or "Not Found" in str(api_error):
                flash('User not found. Please check your Discogs username.', 'error')
            elif "403" in str(api_error) or "Forbidden" in str(api_error):
                flash('Access denied. Please check your token permissions.', 'error')
            else:
                flash(f'Discogs API error: {str(api_error)}', 'error')
            return render_template('setup.html')
        
        logger.info("Discogs API test successful, proceeding with setup...")
        
        # Test encryption
        try:
            encryption_key = generate_encryption_key()
            encrypted_token = encrypt_token(token, encryption_key)
            logger.info("Token encryption successful")
        except Exception as encrypt_error:
            logger.error(f"Token encryption failed: {encrypt_error}")
            flash('Encryption error. Please try again.', 'error')
            return render_template('setup.html')
        
        # Store user data
        try:
            db.execute("""
                INSERT INTO users (discogs_username, user_token)
                VALUES (?, ?)
            """, (username, encrypted_token))
            db.commit()
            logger.info("User data stored in database successfully")
        except Exception as db_error:
            logger.error(f"Database insertion failed: {db_error}")
            flash('Database error. Please try again.', 'error')
            return render_template('setup.html')
        
        # Store encryption key in session (for this deployment model)
        try:
            session['encryption_key'] = encryption_key.decode()
            session['setup_complete'] = True
            logger.info("Session data stored successfully")
        except Exception as session_error:
            logger.error(f"Session storage failed: {session_error}")
            flash('Session error. Please try again.', 'error')
            return render_template('setup.html')
        
        # Initialize Discogs client immediately after setup
        try:
            success = initialize_global_client(
                Config.DATABASE_PATH, username, encrypted_token, encryption_key
            )
            if success:
                logger.info("Discogs client initialized after setup")
            else:
                logger.warning("Failed to initialize Discogs client after setup")
        except Exception as init_error:
            logger.error(f"Error initializing Discogs client after setup: {init_error}")
            # Don't fail setup for this, as it can be retried later
        
        logger.info("Setup completed successfully!")
        flash('Setup completed successfully!', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Unexpected setup error: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash(f'Setup failed: {str(e)}', 'error')
        return render_template('setup.html')

@app.route('/')
@rate_limit(max_requests=30, window=60)
def index():
    """Main collection grid view."""
    try:
        page = max(1, int(request.args.get('page', 1)))
        sort_by = request.args.get('sort', 'date_added')
        sort_order = request.args.get('order', 'desc')
        search_query = request.args.get('q', '').strip()
        
        # Valid sort options
        valid_sorts = ['title', 'artist', 'year', 'date_added', 'rating']
        if sort_by not in valid_sorts:
            sort_by = 'date_added'
        
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        db = get_db()
        
        # Build query
        base_query = "SELECT * FROM albums"
        count_query = "SELECT COUNT(*) as total FROM albums"
        params = []
        
        if search_query:
            where_clause = " WHERE (title LIKE ? OR artist LIKE ?)"
            search_param = f"%{search_query}%"
            base_query += where_clause
            count_query += where_clause
            params = [search_param, search_param]
        
        # Get total count
        total_cursor = db.execute(count_query, params)
        total_albums = total_cursor.fetchone()['total']
        
        # Calculate pagination
        per_page = Config.ITEMS_PER_PAGE
        offset = (page - 1) * per_page
        total_pages = (total_albums + per_page - 1) // per_page
        
        # Get albums for current page
        query = f"{base_query} ORDER BY {sort_by} {sort_order.upper()} LIMIT ? OFFSET ?"
        cursor = db.execute(query, params + [per_page, offset])
        albums = cursor.fetchall()
        
        # Convert to dictionaries and parse JSON fields
        albums_list = []
        for album in albums:
            album_dict = dict(album)
            try:
                album_dict['genres'] = json.loads(album_dict['genres'] or '[]')
                album_dict['styles'] = json.loads(album_dict['styles'] or '[]')
            except json.JSONDecodeError:
                album_dict['genres'] = []
                album_dict['styles'] = []
            albums_list.append(album_dict)
        
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_albums,
            'pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None
        }
        
        response = make_response(render_template(
            'index.html',
            albums=albums_list,
            pagination=pagination,
            sort_by=sort_by,
            sort_order=sort_order,
            search_query=search_query
        ))
        
        return mobile_optimized_response(response)
        
    except Exception as e:
        logger.error(f"Index error: {e}")
        flash('Error loading collection', 'error')
        return render_template('index.html', albums=[], pagination={})

@app.route('/album/<int:album_id>')
@rate_limit(max_requests=60, window=60)
def album_detail(album_id):
    """Album detail view."""
    try:
        db = get_db()
        cursor = db.execute("SELECT * FROM albums WHERE id = ?", (album_id,))
        album = cursor.fetchone()
        
        if not album:
            abort(404)
        
        # Convert to dictionary and parse JSON fields
        album_dict = dict(album)
        try:
            album_dict['genres'] = json.loads(album_dict['genres'] or '[]')
            album_dict['styles'] = json.loads(album_dict['styles'] or '[]')
            album_dict['tracklist'] = json.loads(album_dict['tracklist'] or '[]')
        except json.JSONDecodeError:
            album_dict['genres'] = []
            album_dict['styles'] = []
            album_dict['tracklist'] = []
        
        # Get songs with LRC status
        cursor = db.execute("""
            SELECT id, track_position, title, duration_seconds, record_side, 
                   lrc_content IS NOT NULL as has_lrc, lrc_filename,
                   song_buffer_seconds
            FROM songs 
            WHERE album_id = ? 
            ORDER BY record_side, track_position
        """, (album_id,))
        
        songs = [dict(row) for row in cursor.fetchall()]
        album_dict['songs'] = songs
        
        # Get record side completion status
        cursor = db.execute("""
            SELECT side_label, total_tracks, tracks_with_lrc, is_complete
            FROM record_sides 
            WHERE album_id = ?
            ORDER BY side_label
        """, (album_id,))
        
        record_sides = [dict(row) for row in cursor.fetchall()]
        album_dict['record_sides'] = record_sides
        
        # Get global and album-level buffer settings
        cursor = db.execute("SELECT value FROM settings WHERE key = 'default_song_buffer_seconds'")
        default_buffer = cursor.fetchone()
        global_default = float(default_buffer['value']) if default_buffer else 3.0
        album_dict['global_buffer_default'] = global_default
        
        # Update play count
        db.execute(
            "UPDATE albums SET play_count = play_count + 1, last_played = ? WHERE id = ?",
            (datetime.now().isoformat(), album_id)
        )
        db.commit()
        
        response = make_response(render_template('album_detail.html', album=album_dict))
        return mobile_optimized_response(response)
        
    except Exception as e:
        logger.error(f"Album detail error: {e}")
        abort(500)

@app.route('/random')
@rate_limit(max_requests=30, window=60)
def random_album():
    """Get random album using intelligent algorithm with A/B testing for instant response."""
    try:
        # Get session ID for tracking
        session_id = session.get('session_id')
        if not session_id:
            session_id = secrets.token_urlsafe(16)
            session['session_id'] = session_id
        
        # Get A/B test assignment and configuration
        group, config = get_user_algorithm_config(session_id, str(Config.DATABASE_PATH))
        
        # Use intelligent algorithm with A/B test configuration
        album = get_random_album(str(Config.DATABASE_PATH), session_id)
        
        if not album:
            # Fallback to simple random selection
            db = get_db()
            cursor = db.execute("SELECT * FROM albums ORDER BY RANDOM() LIMIT 1")
            album_row = cursor.fetchone()
            
            if not album_row:
                return jsonify({'error': 'No albums in collection'}), 404
            
            album = dict(album_row)
        
        # Record selection metric for A/B testing
        record_selection_metric(session_id, str(Config.DATABASE_PATH))
        
        # Add feedback parameter to URL to show feedback buttons
        return redirect(url_for('album_detail', album_id=album['id'], feedback=1))
        
    except Exception as e:
        logger.error(f"Random album error: {e}")
        abort(500)

@app.route('/search')
@rate_limit(max_requests=30, window=60)
def search():
    """Search results page."""
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('index'))
    
    return redirect(url_for('index', q=query))

@app.route('/stats')
@rate_limit(max_requests=10, window=60)
def stats():
    """Collection statistics."""
    try:
        db = get_db()
        
        # Basic stats
        cursor = db.execute("SELECT COUNT(*) as total FROM albums")
        total_albums = cursor.fetchone()['total']
        
        cursor = db.execute("SELECT COUNT(DISTINCT artist) as total FROM albums")
        total_artists = cursor.fetchone()['total']
        
        cursor = db.execute("SELECT AVG(year) as avg_year FROM albums WHERE year > 0")
        avg_year = cursor.fetchone()['avg_year'] or 0
        
        # Top genres
        cursor = db.execute("""
            SELECT genres, COUNT(*) as count FROM albums 
            WHERE genres IS NOT NULL AND genres != '[]'
            GROUP BY genres ORDER BY count DESC LIMIT 10
        """)
        genre_data = cursor.fetchall()
        
        # Top artists
        cursor = db.execute("""
            SELECT artist, COUNT(*) as count FROM albums 
            GROUP BY artist ORDER BY count DESC LIMIT 10
        """)
        top_artists = cursor.fetchall()
        
        # Decade breakdown
        cursor = db.execute("""
            SELECT 
                CASE 
                    WHEN year >= 2020 THEN '2020s'
                    WHEN year >= 2010 THEN '2010s'
                    WHEN year >= 2000 THEN '2000s'
                    WHEN year >= 1990 THEN '1990s'
                    WHEN year >= 1980 THEN '1980s'
                    WHEN year >= 1970 THEN '1970s'
                    WHEN year >= 1960 THEN '1960s'
                    WHEN year > 0 THEN 'Pre-1960s'
                    ELSE 'Unknown'
                END as decade,
                COUNT(*) as count
            FROM albums
            GROUP BY decade
            ORDER BY count DESC
        """)
        decades = cursor.fetchall()
        
        stats_data = {
            'total_albums': total_albums,
            'total_artists': total_artists,
            'average_year': round(avg_year, 1) if avg_year else 0,
            'top_artists': [dict(row) for row in top_artists],
            'decades': [dict(row) for row in decades]
        }
        
        response = make_response(render_template('stats.html', stats=stats_data))
        return mobile_optimized_response(response)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        abort(500)

@app.route('/analytics')
@rate_limit(max_requests=10, window=60)
def analytics():
    """Random algorithm analytics dashboard."""
    try:
        response = make_response(render_template('analytics.html'))
        return mobile_optimized_response(response)
        
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        abort(500)

@app.route('/sync', methods=['GET', 'POST'])
@rate_limit(max_requests=15, window=60)  # 15 requests per minute total
def sync():
    """Manual sync trigger with enhanced Discogs integration."""
    if request.method == 'GET':
        # Get current sync status
        sync_status = None
        client = get_global_client()
        if client:
            sync_status = client.get_sync_status()
        
        return render_template('sync.html', sync_status=sync_status)
    
    try:
        user_data = get_user_data()
        if not user_data:
            flash('User configuration not found', 'error')
            return redirect(url_for('setup'))
        
        # Get the global Discogs client
        client = get_global_client()
        if not client:
            flash('Discogs client not initialized', 'error')
            return render_template('sync.html')
        
        if not client.is_online():
            flash('Discogs client is offline. Check your internet connection.', 'error')
            return render_template('sync.html')
        
        # Test connection first
        success, message = client.test_connection()
        if not success:
            flash(f'Connection test failed: {message}', 'error')
            return render_template('sync.html')
        
        # Start background sync
        force_full = request.form.get('force_full', False)
        if client.sync_collection(background=True, force_full=force_full):
            flash('Sync initiated successfully. This may take several minutes.', 'success')
            
            # Schedule cache refresh after sync completion
            def refresh_after_sync():
                import time
                import threading
                
                def check_and_refresh():
                    # Wait for sync to complete (check every 30 seconds)
                    max_wait = 3600  # Maximum 1 hour wait
                    waited = 0
                    
                    while waited < max_wait:
                        time.sleep(30)
                        waited += 30
                        
                        try:
                            sync_status = client.get_sync_status()
                            if sync_status and not sync_status.get('running', False):
                                # Sync completed, refresh cache
                                logger.info("Sync completed, refreshing random algorithm cache")
                                refresh_algorithm_cache(str(Config.DATABASE_PATH))
                                break
                        except Exception as e:
                            logger.error(f"Error checking sync status: {e}")
                            break
                
                # Run in background thread
                thread = threading.Thread(target=check_and_refresh, daemon=True)
                thread.start()
            
            refresh_after_sync()
        else:
            flash('Failed to start sync. Another sync may be in progress.', 'error')
        
        return render_template('sync.html', sync_initiated=True)
        
    except DiscogsAPIError as e:
        logger.error(f"Discogs API error: {e}")
        flash(f'Discogs API error: {str(e)}', 'error')
        return render_template('sync.html')
    except Exception as e:
        logger.error(f"Sync error: {e}")
        flash('Sync failed due to unexpected error', 'error')
        return render_template('sync.html')

# API Routes
@app.route('/api/collection')
@rate_limit(max_requests=60, window=60)
def api_collection():
    """JSON API for collection data."""
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(100, max(1, int(request.args.get('per_page', Config.ITEMS_PER_PAGE))))
        search_query = request.args.get('q', '').strip()
        
        db = get_db()
        
        # Build query
        base_query = "SELECT * FROM albums"
        count_query = "SELECT COUNT(*) as total FROM albums"
        params = []
        
        if search_query:
            where_clause = " WHERE (title LIKE ? OR artist LIKE ?)"
            search_param = f"%{search_query}%"
            base_query += where_clause
            count_query += where_clause
            params = [search_param, search_param]
        
        # Get total count
        total_cursor = db.execute(count_query, params)
        total_albums = total_cursor.fetchone()['total']
        
        # Get albums
        offset = (page - 1) * per_page
        query = f"{base_query} ORDER BY date_added DESC LIMIT ? OFFSET ?"
        cursor = db.execute(query, params + [per_page, offset])
        albums = cursor.fetchall()
        
        # Convert to list of dictionaries
        albums_list = []
        for album in albums:
            album_dict = dict(album)
            try:
                album_dict['genres'] = json.loads(album_dict['genres'] or '[]')
                album_dict['styles'] = json.loads(album_dict['styles'] or '[]')
            except json.JSONDecodeError:
                album_dict['genres'] = []
                album_dict['styles'] = []
            albums_list.append(album_dict)
        
        return jsonify({
            'albums': albums_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_albums,
                'pages': (total_albums + per_page - 1) // per_page
            }
        })
        
    except Exception as e:
        logger.error(f"API collection error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/album/<int:album_id>')
@rate_limit(max_requests=60, window=60)
def api_album_detail(album_id):
    """JSON API for album detail."""
    try:
        db = get_db()
        cursor = db.execute("SELECT * FROM albums WHERE id = ?", (album_id,))
        album = cursor.fetchone()
        
        if not album:
            return jsonify({'error': 'Album not found'}), 404
        
        # Convert to dictionary and parse JSON fields
        album_dict = dict(album)
        try:
            album_dict['genres'] = json.loads(album_dict['genres'] or '[]')
            album_dict['styles'] = json.loads(album_dict['styles'] or '[]')
            album_dict['tracklist'] = json.loads(album_dict['tracklist'] or '[]')
        except json.JSONDecodeError:
            album_dict['genres'] = []
            album_dict['styles'] = []
            album_dict['tracklist'] = []
        
        return jsonify(album_dict)
        
    except Exception as e:
        logger.error(f"API album detail error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/album/<int:album_id>/edit', methods=['GET', 'POST'])
@rate_limit(max_requests=30, window=300)
def edit_album(album_id):
    """Edit album with image and LRC file upload."""
    try:
        db = get_db()
        
        if request.method == 'GET':
            cursor = db.execute("SELECT * FROM albums WHERE id = ?", (album_id,))
            album = cursor.fetchone()
            
            if not album:
                flash('Album not found', 'error')
                return redirect(url_for('index'))
                
            return render_template('edit_album.html', album=album)
        
        # Handle POST request - save changes
        album_data = {}
        
        # Handle album buffer setting from form
        album_buffer = request.form.get('album_buffer_seconds')
        if album_buffer:
            try:
                album_data['song_buffer_seconds'] = float(album_buffer)
            except ValueError:
                pass
        elif album_buffer == '':
            # Empty string means remove album-specific setting
            album_data['song_buffer_seconds'] = None
        
        # Handle image upload
        if 'custom_image' in request.files:
            file = request.files['custom_image']
            if file and file.filename:
                if file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    # Create uploads directory if it doesn't exist
                    upload_dir = Config.CACHE_DIR / 'uploads'
                    upload_dir.mkdir(exist_ok=True)
                    
                    # Save file with unique name
                    import uuid
                    filename = f"{album_id}_{uuid.uuid4().hex[:8]}.{file.filename.rsplit('.', 1)[1].lower()}"
                    filepath = upload_dir / filename
                    file.save(str(filepath))
                    
                    album_data['custom_image'] = f"/uploads/{filename}"
                else:
                    flash('Invalid image format. Please use PNG, JPG, JPEG, GIF, or WebP.', 'error')
                    return redirect(request.url)
        
        # Handle LRC file upload (legacy)
        if 'lrc_file' in request.files:
            file = request.files['lrc_file']
            if file and file.filename:
                if file.filename.lower().endswith('.lrc'):
                    # Read and validate LRC content
                    lrc_content = file.read().decode('utf-8', errors='ignore')
                    
                    # Basic LRC validation - should contain [mm:ss.xx] patterns
                    import re
                    if re.search(r'\[\d{2}:\d{2}\.\d{2}\]', lrc_content):
                        album_data['lrc_lyrics'] = lrc_content
                        album_data['lyrics_filename'] = file.filename
                        flash('Legacy LRC lyrics uploaded successfully!', 'success')
                    else:
                        flash('Invalid LRC format. Please ensure the file contains proper timestamps [mm:ss.xx].', 'error')
                        return redirect(request.url)
                else:
                    flash('Invalid file format. Please upload an LRC file.', 'error')
                    return redirect(request.url)
        
        # Update database if we have changes
        if album_data:
            set_clause = ', '.join([f"{key} = ?" for key in album_data.keys()])
            values = list(album_data.values()) + [album_id]
            
            db.execute(f"UPDATE albums SET {set_clause} WHERE id = ?", values)
            db.commit()
            flash('Album updated successfully!', 'success')
        
        return redirect(url_for('album_detail', album_id=album_id))
        
    except Exception as e:
        logger.error(f"Edit album error: {e}")
        flash('Error updating album', 'error')
        return redirect(url_for('album_detail', album_id=album_id))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files."""
    return send_from_directory(str(Config.CACHE_DIR / 'uploads'), filename)

@app.route('/album/<int:album_id>/lyrics')
def lyrics_display(album_id):
    """Synchronized lyrics display screen."""
    try:
        db = get_db()
        cursor = db.execute("SELECT * FROM albums WHERE id = ?", (album_id,))
        album = cursor.fetchone()
        
        if not album:
            flash('Album not found', 'error')
            return redirect(url_for('index'))
        
        if not album['lrc_lyrics']:
            flash('No lyrics available for this album', 'error')
            return redirect(url_for('album_detail', album_id=album_id))
        
        return render_template('lyrics_display.html', album=album)
        
    except Exception as e:
        logger.error(f"Lyrics display error: {e}")
        flash('Error loading lyrics', 'error')
        return redirect(url_for('album_detail', album_id=album_id))

@app.route('/api/album/<int:album_id>/lyrics')
@rate_limit(max_requests=60, window=60)
def api_lyrics(album_id):
    """JSON API for album lyrics."""
    try:
        db = get_db()
        cursor = db.execute("SELECT lrc_lyrics, lyrics_filename FROM albums WHERE id = ?", (album_id,))
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'error': 'Album not found'}), 404
        
        if not result['lrc_lyrics']:
            return jsonify({'error': 'No lyrics available'}), 404
        
        return jsonify({
            'lyrics': result['lrc_lyrics'],
            'filename': result['lyrics_filename']
        })
        
    except Exception as e:
        logger.error(f"API lyrics error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/album/<int:album_id>/songs')
@rate_limit(max_requests=60, window=60)
def api_album_songs(album_id):
    """JSON API for album songs with LRC status."""
    try:
        db = get_db()
        
        # Get album buffer setting and global default
        cursor = db.execute("SELECT song_buffer_seconds FROM albums WHERE id = ?", (album_id,))
        album = cursor.fetchone()
        if not album:
            return jsonify({'error': 'Album not found'}), 404
        
        # Get global default buffer
        cursor = db.execute("SELECT value FROM settings WHERE key = 'default_song_buffer_seconds'")
        default_buffer = cursor.fetchone()
        global_default = float(default_buffer['value']) if default_buffer else 3.0
        
        # Get album-level buffer or use global default
        album_buffer = album['song_buffer_seconds'] or global_default
        
        # Get all songs for this album
        cursor = db.execute("""
            SELECT id, track_position, title, duration_seconds, record_side, 
                   lrc_content IS NOT NULL as has_lrc, lrc_filename,
                   song_buffer_seconds, uploaded_at, updated_at
            FROM songs 
            WHERE album_id = ? 
            ORDER BY record_side, track_position
        """, (album_id,))
        
        songs = []
        for row in cursor.fetchall():
            song = dict(row)
            # Apply buffer precedence: song > album > collection
            effective_buffer = song['song_buffer_seconds'] or album_buffer
            song['effective_buffer_seconds'] = effective_buffer
            songs.append(song)
        
        # Get record side completion status
        cursor = db.execute("""
            SELECT side_label, total_tracks, tracks_with_lrc, is_complete
            FROM record_sides 
            WHERE album_id = ?
            ORDER BY side_label
        """, (album_id,))
        
        record_sides = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'album_id': album_id,
            'global_default_buffer': global_default,
            'album_buffer': album_buffer,
            'songs': songs,
            'record_sides': record_sides
        })
        
    except Exception as e:
        logger.error(f"API album songs error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/song/<int:song_id>/lrc', methods=['GET', 'POST', 'DELETE'])
@rate_limit(max_requests=30, window=60)
def api_song_lrc(song_id):
    """JSON API for individual song LRC files."""
    try:
        db = get_db()
        
        if request.method == 'GET':
            cursor = db.execute("""
                SELECT lrc_content, lrc_filename, song_buffer_seconds, title, record_side
                FROM songs WHERE id = ?
            """, (song_id,))
            song = cursor.fetchone()
            
            if not song:
                return jsonify({'error': 'Song not found'}), 404
            
            return jsonify(dict(song))
        
        elif request.method == 'POST':
            # Handle LRC upload or update
            data = request.get_json() or {}
            lrc_content = data.get('lrc_content', '').strip()
            lrc_filename = data.get('lrc_filename', '')
            buffer_seconds = data.get('buffer_seconds')
            
            if not lrc_content:
                return jsonify({'error': 'LRC content is required'}), 400
            
            # Basic LRC validation
            import re
            if not re.search(r'\[\d{2}:\d{2}\.\d{2}\]', lrc_content):
                return jsonify({'error': 'Invalid LRC format. Must contain timestamps like [mm:ss.xx]'}), 400
            
            # Update song with LRC data
            cursor = db.execute("""
                UPDATE songs 
                SET lrc_content = ?, lrc_filename = ?, song_buffer_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (lrc_content, lrc_filename, buffer_seconds, song_id))
            
            if cursor.rowcount == 0:
                return jsonify({'error': 'Song not found'}), 404
            
            db.commit()
            
            return jsonify({
                'success': True,
                'message': 'LRC file uploaded successfully'
            })
        
        elif request.method == 'DELETE':
            # Remove LRC content
            cursor = db.execute("""
                UPDATE songs 
                SET lrc_content = NULL, lrc_filename = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (song_id,))
            
            if cursor.rowcount == 0:
                return jsonify({'error': 'Song not found'}), 404
            
            db.commit()
            
            return jsonify({
                'success': True,
                'message': 'LRC file removed successfully'
            })
        
    except Exception as e:
        logger.error(f"API song LRC error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/settings/buffer', methods=['POST'])
@rate_limit(max_requests=10, window=60)
def api_buffer_settings():
    """JSON API for buffer settings."""
    try:
        db = get_db()
        data = request.get_json() or {}
        global_default = data.get('global_default')
        album_buffer = data.get('album_buffer')
        album_id = data.get('album_id')
        
        # Update global setting
        if global_default is not None:
            cursor = db.execute("""
                UPDATE settings 
                SET value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE key = 'default_song_buffer_seconds'
            """, (str(global_default),))
            
            if cursor.rowcount == 0:
                # Insert if doesn't exist
                db.execute("""
                    INSERT INTO settings (key, value, description)
                    VALUES ('default_song_buffer_seconds', ?, 'Default buffer time between songs in seconds when combining LRC files')
                """, (str(global_default),))
        
        # Update album setting
        if album_id:
            db.execute("""
                UPDATE albums 
                SET song_buffer_seconds = ?
                WHERE id = ?
            """, (album_buffer, album_id))
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Buffer settings updated successfully'
        })
        
    except Exception as e:
        logger.error(f"API buffer settings error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/album/<int:album_id>/combine-lrc', methods=['POST'])
@rate_limit(max_requests=5, window=300)
def api_combine_lrc(album_id):
    """JSON API to combine LRC files for a record side."""
    try:
        db = get_db()
        data = request.get_json() or {}
        side = data.get('side', 'A')
        
        if side not in ['A', 'B', 'C', 'D']:
            return jsonify({'error': 'Invalid record side'}), 400
        
        # Get all songs for this side with LRC content, ordered by track position
        cursor = db.execute("""
            SELECT id, track_position, title, duration_seconds, lrc_content, 
                   song_buffer_seconds
            FROM songs 
            WHERE album_id = ? AND record_side = ? AND lrc_content IS NOT NULL
            ORDER BY track_position
        """, (album_id, side))
        
        songs = cursor.fetchall()
        
        if not songs:
            return jsonify({'error': f'No songs with LRC content found for Side {side}'}), 404
        
        # Get buffer settings
        cursor = db.execute("SELECT song_buffer_seconds FROM albums WHERE id = ?", (album_id,))
        album = cursor.fetchone()
        
        cursor = db.execute("SELECT value FROM settings WHERE key = 'default_song_buffer_seconds'")
        default_buffer = cursor.fetchone()
        global_default = float(default_buffer['value']) if default_buffer else 3.0
        album_buffer = album['song_buffer_seconds'] or global_default
        
        # Combine LRC files
        combined_lrc_lines = []
        cumulative_offset = 0.0
        
        # Add metadata
        cursor = db.execute("SELECT title, artist FROM albums WHERE id = ?", (album_id,))
        album_info = cursor.fetchone()
        
        combined_lrc_lines.append(f"[ar:{album_info['artist']}]")
        combined_lrc_lines.append(f"[al:{album_info['title']} (Side {side})]")
        combined_lrc_lines.append(f"[ti:Side {side} Combined]")
        combined_lrc_lines.append("")
        
        import re
        
        for i, song in enumerate(songs):
            # Add track marker
            combined_lrc_lines.append(f"[-- Track {song['track_position']}: {song['title']} --]")
            
            # Parse and adjust timestamps
            lines = song['lrc_content'].strip().split('\n')
            for line in lines:
                line = line.strip()
                match = re.match(r'(\[\d{2}:\d{2}\.\d{2}\])(.*)', line)
                if match:
                    timestamp_str, lyric_text = match.groups()
                    # Parse timestamp
                    time_match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2})\]', timestamp_str)
                    if time_match:
                        minutes, seconds, hundredths = map(int, time_match.groups())
                        original_seconds = minutes * 60 + seconds + hundredths / 100.0
                        new_seconds = original_seconds + cumulative_offset
                        
                        # Format new timestamp
                        new_minutes = int(new_seconds / 60)
                        new_secs = int(new_seconds % 60)
                        new_hundredths = int((new_seconds - int(new_seconds)) * 100)
                        new_timestamp = f"[{new_minutes:02d}:{new_secs:02d}.{new_hundredths:02d}]"
                        
                        combined_lrc_lines.append(f"{new_timestamp}{lyric_text}")
                elif not re.match(r'\[(ar|al|ti|au|length|by|offset):.*\]', line):
                    # Keep non-metadata lines
                    combined_lrc_lines.append(line)
            
            # Add buffer time for next track (except for last track)
            if i < len(songs) - 1:
                # Use song-specific buffer or fall back to album/global default
                buffer_seconds = song['song_buffer_seconds'] or album_buffer
                cumulative_offset += (song['duration_seconds'] or 180) + buffer_seconds  # Default 3min if no duration
            else:
                # For last track, just add the duration without buffer
                cumulative_offset += (song['duration_seconds'] or 180)
        
        # Store combined LRC
        combined_lrc = '\n'.join(combined_lrc_lines)
        column_name = f'combined_lrc_{side.lower()}_side'
        timestamp_column = f'combined_lrc_timestamp_{side.lower()}'
        
        db.execute(f"""
            UPDATE albums 
            SET {column_name} = ?, {timestamp_column} = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (combined_lrc, album_id))
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully combined {len(songs)} LRC files for Side {side}',
            'track_count': len(songs),
            'total_duration_minutes': round(cumulative_offset / 60, 1)
        })
        
    except Exception as e:
        logger.error(f"API combine LRC error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/album/<int:album_id>/combined-lrc/<side>')
@rate_limit(max_requests=30, window=60)
def api_get_combined_lrc(album_id, side):
    """JSON API to get combined LRC content for a record side."""
    try:
        if side not in ['A', 'B', 'C', 'D']:
            return jsonify({'error': 'Invalid record side'}), 400
        
        db = get_db()
        column_name = f'combined_lrc_{side.lower()}_side'
        timestamp_column = f'combined_lrc_timestamp_{side.lower()}'
        
        cursor = db.execute(f"""
            SELECT {column_name} as lrc_content, {timestamp_column} as timestamp
            FROM albums WHERE id = ?
        """, (album_id,))
        
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'error': 'Album not found'}), 404
        
        if not result['lrc_content']:
            return jsonify({'error': f'No combined LRC content found for Side {side}'}), 404
        
        return jsonify({
            'lrc_content': result['lrc_content'],
            'side': side,
            'timestamp': result['timestamp']
        })
        
    except Exception as e:
        logger.error(f"API get combined LRC error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sync/status')
@rate_limit(max_requests=30, window=60)
def api_sync_status():
    """JSON API for sync status."""
    try:
        client = get_global_client()
        if not client:
            return jsonify({
                'status': 'offline',
                'message': 'Discogs client not initialized'
            }), 503
        
        sync_status = client.get_sync_status()
        collection_stats = client.get_collection_stats()
        
        return jsonify({
            'sync_status': sync_status,
            'collection_stats': collection_stats,
            'client_online': client.is_online()
        })
        
    except Exception as e:
        logger.error(f"API sync status error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sync/start', methods=['POST'])
@rate_limit(max_requests=1, window=300)
def api_sync_start():
    """JSON API to start sync."""
    try:
        client = get_global_client()
        if not client:
            return jsonify({
                'success': False,
                'message': 'Discogs client not initialized'
            }), 503
        
        if not client.is_online():
            return jsonify({
                'success': False,
                'message': 'Discogs client is offline'
            }), 503
        
        # Get parameters
        data = request.get_json() or {}
        force_full = data.get('force_full', False)
        
        # Test connection first
        success, message = client.test_connection()
        if not success:
            return jsonify({
                'success': False,
                'message': f'Connection test failed: {message}'
            }), 400
        
        # Start sync
        if client.sync_collection(background=True, force_full=force_full):
            return jsonify({
                'success': True,
                'message': 'Sync started successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to start sync (another sync may be in progress)'
            }), 409
        
    except DiscogsAPIError as e:
        logger.error(f"API sync start error: {e}")
        return jsonify({
            'success': False,
            'message': f'Discogs API error: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"API sync start error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/sync/cancel', methods=['POST'])
@rate_limit(max_requests=10, window=60)
def api_sync_cancel():
    """JSON API to cancel sync."""
    try:
        client = get_global_client()
        if not client:
            return jsonify({
                'success': False,
                'message': 'Discogs client not initialized'
            }), 503
        
        if client.cancel_sync():
            return jsonify({
                'success': True,
                'message': 'Sync cancellation requested'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No active sync to cancel'
            }), 400
        
    except Exception as e:
        logger.error(f"API sync cancel error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/search')
@rate_limit(max_requests=30, window=60)
def api_search():
    """JSON API for Discogs search."""
    try:
        query = request.args.get('q', '').strip()
        limit = min(20, max(1, int(request.args.get('limit', 10))))
        
        if not query:
            return jsonify({'error': 'Query parameter required'}), 400
        
        client = get_global_client()
        if not client or not client.is_online():
            return jsonify({
                'error': 'Search unavailable (client offline)',
                'results': []
            }), 503
        
        results = client.search_releases(query, limit)
        
        return jsonify({
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Random Algorithm API Routes
@app.route('/api/random')
@rate_limit(max_requests=30, window=60)
def api_random_album():
    """JSON API for intelligent random album selection."""
    try:
        # Get session ID for tracking
        session_id = session.get('session_id')
        if not session_id:
            session_id = secrets.token_urlsafe(16)
            session['session_id'] = session_id
        
        # Use intelligent algorithm
        album = get_random_album(str(Config.DATABASE_PATH), session_id)
        
        if not album:
            return jsonify({'error': 'No albums in collection'}), 404
        
        return jsonify(album)
        
    except Exception as e:
        logger.error(f"API random album error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/random/feedback', methods=['POST'])
@rate_limit(max_requests=60, window=60)
def api_random_feedback():
    """JSON API for recording user feedback on random selections."""
    try:
        data = request.get_json() or {}
        album_id = data.get('album_id')
        feedback = data.get('feedback')  # -1, 0, 1
        
        if album_id is None or feedback is None:
            return jsonify({'error': 'album_id and feedback are required'}), 400
        
        if feedback not in [-1, 0, 1]:
            return jsonify({'error': 'feedback must be -1, 0, or 1'}), 400
        
        session_id = session.get('session_id', 'anonymous')
        
        record_album_feedback(str(Config.DATABASE_PATH), album_id, feedback, session_id)
        
        # Also record for A/B testing
        record_feedback_metric(session_id, feedback, str(Config.DATABASE_PATH))
        
        return jsonify({
            'success': True,
            'message': 'Feedback recorded successfully'
        })
        
    except Exception as e:
        logger.error(f"API random feedback error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/random/stats')
@rate_limit(max_requests=10, window=60)
def api_random_stats():
    """JSON API for random algorithm statistics."""
    try:
        stats = get_algorithm_statistics(str(Config.DATABASE_PATH))
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"API random stats error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/random/refresh', methods=['POST'])
@rate_limit(max_requests=5, window=300)
def api_random_refresh():
    """JSON API to refresh random algorithm cache."""
    try:
        refresh_algorithm_cache(str(Config.DATABASE_PATH))
        
        return jsonify({
            'success': True,
            'message': 'Algorithm cache refreshed successfully'
        })
        
    except Exception as e:
        logger.error(f"API random refresh error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# A/B Testing API Routes
@app.route('/api/ab-tests')
@rate_limit(max_requests=10, window=60)
def api_ab_tests():
    """JSON API for A/B test management."""
    try:
        manager = get_ab_manager(str(Config.DATABASE_PATH))
        tests = manager.list_tests()
        
        # Convert datetime objects to ISO strings for JSON serialization
        for test in tests:
            for key in ['start_date', 'end_date', 'created_at']:
                if key in test and test[key]:
                    test[key] = test[key].isoformat()
        
        return jsonify({
            'tests': tests,
            'count': len(tests)
        })
        
    except Exception as e:
        logger.error(f"API A/B tests error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ab-tests/<test_name>/results')
@rate_limit(max_requests=10, window=60)
def api_ab_test_results(test_name):
    """JSON API for A/B test results."""
    try:
        manager = get_ab_manager(str(Config.DATABASE_PATH))
        results = manager.get_test_results(test_name)
        
        if not results:
            return jsonify({'error': 'Test not found or insufficient data'}), 404
        
        return jsonify(asdict(results))
        
    except Exception as e:
        logger.error(f"API A/B test results error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/image-proxy/<path:url>')
def image_proxy(url):
    """Proxy for Discogs images to handle authentication and CORS."""
    import requests
    from flask import Response
    
    try:
        # Decode the URL if it was encoded
        import urllib.parse
        decoded_url = urllib.parse.unquote(url)
        
        # Ensure it's a Discogs image URL for security
        if not decoded_url.startswith(('https://i.discogs.com/', 'https://img.discogs.com/')):
            logger.warning(f"Blocked non-Discogs image URL: {decoded_url}")
            return get_placeholder_url('thumbnails'), 302
        
        # Get the global client to use its authentication
        client = get_global_client()
        
        # Fetch the image with authentication headers
        headers = {
            'User-Agent': Config.DISCOGS_USER_AGENT,
        }
        
        # Add authorization if we have a token
        if client and hasattr(client, '_client') and client._client:
            # The discogs_client library handles auth internally, but we can add headers
            import os
            token = os.environ.get('DISCOGS_TOKEN')
            if token:
                headers['Authorization'] = f'Discogs token={token}'
        
        response = requests.get(decoded_url, headers=headers, timeout=10, stream=True)
        
        if response.status_code == 200:
            # Stream the image back to the client
            return Response(
                response.iter_content(chunk_size=1024),
                content_type=response.headers.get('Content-Type', 'image/jpeg'),
                headers={
                    'Cache-Control': 'public, max-age=86400',  # Cache for 1 day
                    'Access-Control-Allow-Origin': '*'
                }
            )
        else:
            logger.warning(f"Failed to fetch image: {response.status_code} for {decoded_url}")
            return get_placeholder_url('thumbnails'), 302
            
    except Exception as e:
        logger.error(f"Image proxy error: {e}")
        return get_placeholder_url('thumbnails'), 302

@app.route('/api/ab-tests/create', methods=['POST'])
@rate_limit(max_requests=5, window=300)
def api_create_ab_test():
    """JSON API to create a new A/B test."""
    try:
        data = request.get_json() or {}
        test_type = data.get('test_type')
        
        if not test_type:
            return jsonify({'error': 'test_type is required'}), 400
        
        manager = get_ab_manager(str(Config.DATABASE_PATH))
        
        # Create predefined test configurations
        if test_type == 'rating_weight':
            test_config = create_rating_weight_test()
        elif test_type == 'diversity_weight':
            test_config = create_diversity_weight_test()
        else:
            return jsonify({'error': 'Unknown test type'}), 400
        
        success = manager.create_test(test_config)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'A/B test "{test_config.test_name}" created successfully',
                'test_name': test_config.test_name
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to create A/B test'
            }), 500
        
    except Exception as e:
        logger.error(f"API create A/B test error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/ab-tests/<test_name>/stop', methods=['POST'])
@rate_limit(max_requests=10, window=60)
def api_stop_ab_test(test_name):
    """JSON API to stop an A/B test."""
    try:
        manager = get_ab_manager(str(Config.DATABASE_PATH))
        success = manager.stop_test(test_name)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'A/B test "{test_name}" stopped successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to stop A/B test'
            }), 500
        
    except Exception as e:
        logger.error(f"API stop A/B test error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Image Cache Routes
@app.route('/cache/<path:filename>')
def serve_cached_image(filename):
    """Serve cached images with proper headers."""
    try:
        cache = get_image_cache()
        if not cache:
            abort(404)
        
        file_path = cache.cache_dir / filename
        
        if not file_path.exists() or not file_path.is_file():
            # Try to serve placeholder instead
            if 'thumbnail' in filename:
                placeholder_path = cache.get_placeholder_path('thumbnails')
            else:
                placeholder_path = cache.get_placeholder_path('detail')
            
            if not os.path.exists(placeholder_path):
                abort(404)
            
            file_path = Path(placeholder_path)
        
        # Determine content type
        if file_path.suffix.lower() == '.webp':
            mimetype = 'image/webp'
        else:
            mimetype = 'image/jpeg'
        
        # Create response with caching headers
        response = send_file(
            str(file_path),
            mimetype=mimetype,
            as_attachment=False,
            conditional=True
        )
        
        # Set cache headers (1 week for cached images)
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        response.headers['ETag'] = f'"{file_path.stat().st_mtime}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error serving cached image {filename}: {e}")
        abort(404)

@app.route('/api/cache/stats')
@rate_limit(max_requests=10, window=60)
def api_cache_stats():
    """JSON API for cache statistics."""
    try:
        cache = get_image_cache()
        if not cache:
            return jsonify({'error': 'Cache not initialized'}), 503
        
        stats = cache.get_cache_stats()
        
        # Convert dataclass to dict for JSON serialization
        from dataclasses import asdict
        stats_dict = asdict(stats)
        
        # Convert datetime to ISO string if present
        if stats_dict.get('last_cleanup'):
            stats_dict['last_cleanup'] = stats_dict['last_cleanup'].isoformat()
        
        return jsonify(stats_dict)
        
    except Exception as e:
        logger.error(f"API cache stats error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/clear', methods=['POST'])
@rate_limit(max_requests=1, window=300)
def api_cache_clear():
    """JSON API to clear image cache."""
    try:
        cache = get_image_cache()
        if not cache:
            return jsonify({'error': 'Cache not initialized'}), 503
        
        if cache.clear_cache():
            return jsonify({
                'success': True,
                'message': 'Cache cleared successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to clear cache'
            }), 500
        
    except Exception as e:
        logger.error(f"API cache clear error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/cache/preload', methods=['POST'])
@rate_limit(max_requests=5, window=300)
def api_cache_preload():
    """JSON API to preload images for current page."""
    try:
        cache = get_image_cache()
        if not cache:
            return jsonify({'error': 'Cache not initialized'}), 503
        
        data = request.get_json() or {}
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'error': 'No URLs provided'}), 400
        
        # Limit the number of URLs to prevent abuse
        urls = urls[:20]
        
        # Start preloading in background
        def progress_callback(completed, total, current_url):
            # Could emit progress via WebSocket if needed
            logger.debug(f"Preload progress: {completed}/{total} - {current_url}")
        
        results = cache.preload_images(urls, progress_callback)
        
        success_count = sum(1 for success in results.values() if success)
        
        return jsonify({
            'success': True,
            'preloaded': success_count,
            'total': len(urls),
            'results': results
        })
        
    except Exception as e:
        logger.error(f"API cache preload error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Template context processors for image cache
@app.context_processor
def inject_image_helpers():
    """Inject image helper functions into templates."""
    import urllib.parse
    
    def get_best_image_url(album_or_url, size_type='thumbnails'):
        """Get the best available image URL (custom first, then Discogs)."""
        if isinstance(album_or_url, dict):
            # If we have an album dict, check for custom image first
            if album_or_url.get('custom_image'):
                return album_or_url['custom_image']
            # Fall back to cover_url
            url = album_or_url.get('cover_url')
        else:
            # Direct URL passed
            url = album_or_url
            
        if not url:
            return get_placeholder_url(size_type)
            
        # If it's a Discogs URL, proxy it
        if 'discogs' in url.lower():
            encoded_url = urllib.parse.quote(url, safe='')
            return f'/image-proxy/{encoded_url}'
        
        return url
    
    return {
        'get_cached_image_url': get_cached_image_url,
        'get_placeholder_url': get_placeholder_url,
        'get_thumbnail_url': lambda album_or_url: get_best_image_url(album_or_url, 'thumbnails'),
        'get_detail_image_url': lambda album_or_url: get_best_image_url(album_or_url, 'detail'),
        'get_best_image_url': get_best_image_url
    }

if __name__ == '__main__':
    # Initialize database if it doesn't exist
    if not Config.DATABASE_PATH.exists():
        from init_db import init_database
        init_database()
    
    # Initialize Discogs client for development
    try:
        with app.app_context():
            if is_setup_complete():
                db = get_db()
                user_data = get_user_discogs_data(db)
                if user_data:
                    username, encrypted_token = user_data
                    # For development, you might need to set encryption key differently
                    logger.info("Found user data for Discogs client initialization")
    except Exception as e:
        logger.error(f"Error during development initialization: {e}")
    
    # Run development server
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )