#!/usr/bin/env python3
"""Database initialization script for VinylVault."""

import sqlite3
from pathlib import Path
from config import Config

def init_database():
    """Initialize the VinylVault database with required tables."""
    
    # Ensure cache directory exists
    Config.CACHE_DIR.mkdir(exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(str(Config.DATABASE_PATH))
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Users table (single user for Pi deployment)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            discogs_username TEXT NOT NULL,
            user_token TEXT NOT NULL,
            last_sync TIMESTAMP,
            total_items INTEGER DEFAULT 0
        );
    """)
    
    # Albums cache
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY,
            discogs_id INTEGER UNIQUE NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
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
    """)
    
    # Sync status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY,
            sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            items_synced INTEGER,
            status TEXT
        );
    """)
    
    # Random selections cache (for instant random button response)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS random_cache (
            id INTEGER PRIMARY KEY,
            album_id INTEGER,
            weight REAL DEFAULT 1.0,
            last_served TIMESTAMP,
            FOREIGN KEY (album_id) REFERENCES albums (id)
        );
    """)
    
    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_discogs_id ON albums (discogs_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums (artist);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_year ON albums (year);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_rating ON albums (rating);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_date_added ON albums (date_added);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_random_cache_weight ON random_cache (weight);")
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print(f"Database initialized at: {Config.DATABASE_PATH}")
    print("Tables created: users, albums, sync_log, random_cache")

if __name__ == "__main__":
    init_database()