#!/usr/bin/env python3
"""Database migration script to add LRC support with individual songs and record sides."""

import sqlite3
import json
from pathlib import Path
from config import Config

def migrate_database():
    """Add LRC support with songs, record sides, and buffer settings."""
    
    # Connect to database
    conn = sqlite3.connect(str(Config.DATABASE_PATH))
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    print("Starting LRC support migration...")
    
    try:
        # 1. Add settings table for global configuration
        print("Creating settings table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Insert default song buffer setting (3 seconds)
        cursor.execute("""
            INSERT OR IGNORE INTO settings (key, value, description)
            VALUES ('default_song_buffer_seconds', '3.0', 'Default buffer time between songs in seconds when combining LRC files')
        """)
        
        # 2. Add new columns to albums table for album-level settings
        print("Adding album-level buffer settings...")
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(albums)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'song_buffer_seconds' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN song_buffer_seconds REAL DEFAULT NULL")
        
        if 'lrc_lyrics' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN lrc_lyrics TEXT DEFAULT NULL")
            
        if 'lyrics_filename' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN lyrics_filename TEXT DEFAULT NULL")
        
        if 'combined_lrc_a_side' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN combined_lrc_a_side TEXT DEFAULT NULL")
            
        if 'combined_lrc_b_side' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN combined_lrc_b_side TEXT DEFAULT NULL")
            
        if 'combined_lrc_timestamp_a' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN combined_lrc_timestamp_a TIMESTAMP DEFAULT NULL")
            
        if 'combined_lrc_timestamp_b' not in columns:
            cursor.execute("ALTER TABLE albums ADD COLUMN combined_lrc_timestamp_b TIMESTAMP DEFAULT NULL")
        
        # 3. Create songs table for individual song LRC files
        print("Creating songs table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY,
                album_id INTEGER NOT NULL,
                track_position INTEGER NOT NULL,
                title TEXT NOT NULL,
                duration_seconds REAL DEFAULT NULL,
                record_side TEXT DEFAULT 'A' CHECK (record_side IN ('A', 'B', 'C', 'D')),
                lrc_content TEXT DEFAULT NULL,
                lrc_filename TEXT DEFAULT NULL,
                song_buffer_seconds REAL DEFAULT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (album_id) REFERENCES albums (id) ON DELETE CASCADE,
                UNIQUE(album_id, track_position, record_side)
            );
        """)
        
        # 4. Create record_sides table to track completion status
        print("Creating record_sides table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS record_sides (
                id INTEGER PRIMARY KEY,
                album_id INTEGER NOT NULL,
                side_label TEXT NOT NULL CHECK (side_label IN ('A', 'B', 'C', 'D')),
                total_tracks INTEGER DEFAULT 0,
                tracks_with_lrc INTEGER DEFAULT 0,
                is_complete BOOLEAN DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (album_id) REFERENCES albums (id) ON DELETE CASCADE,
                UNIQUE(album_id, side_label)
            );
        """)
        
        # 5. Create indexes for performance
        print("Creating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_album_id ON songs (album_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_record_side ON songs (record_side);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_songs_track_position ON songs (track_position);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_record_sides_album_id ON record_sides (album_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_record_sides_complete ON record_sides (is_complete);")
        
        # 6. Create triggers to maintain record_sides completeness
        print("Creating database triggers...")
        
        # Trigger to update record_sides when songs are inserted/updated/deleted
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_record_sides_after_song_insert
            AFTER INSERT ON songs
            BEGIN
                INSERT OR REPLACE INTO record_sides (album_id, side_label, total_tracks, tracks_with_lrc, is_complete, last_updated)
                SELECT 
                    NEW.album_id,
                    NEW.record_side,
                    COUNT(*),
                    SUM(CASE WHEN lrc_content IS NOT NULL THEN 1 ELSE 0 END),
                    CASE WHEN COUNT(*) = SUM(CASE WHEN lrc_content IS NOT NULL THEN 1 ELSE 0 END) 
                         AND COUNT(*) > 0 THEN 1 ELSE 0 END,
                    CURRENT_TIMESTAMP
                FROM songs 
                WHERE album_id = NEW.album_id AND record_side = NEW.record_side;
            END;
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_record_sides_after_song_update
            AFTER UPDATE ON songs
            BEGIN
                INSERT OR REPLACE INTO record_sides (album_id, side_label, total_tracks, tracks_with_lrc, is_complete, last_updated)
                SELECT 
                    NEW.album_id,
                    NEW.record_side,
                    COUNT(*),
                    SUM(CASE WHEN lrc_content IS NOT NULL THEN 1 ELSE 0 END),
                    CASE WHEN COUNT(*) = SUM(CASE WHEN lrc_content IS NOT NULL THEN 1 ELSE 0 END) 
                         AND COUNT(*) > 0 THEN 1 ELSE 0 END,
                    CURRENT_TIMESTAMP
                FROM songs 
                WHERE album_id = NEW.album_id AND record_side = NEW.record_side;
            END;
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_record_sides_after_song_delete
            AFTER DELETE ON songs
            BEGIN
                INSERT OR REPLACE INTO record_sides (album_id, side_label, total_tracks, tracks_with_lrc, is_complete, last_updated)
                SELECT 
                    OLD.album_id,
                    OLD.record_side,
                    COUNT(*),
                    SUM(CASE WHEN lrc_content IS NOT NULL THEN 1 ELSE 0 END),
                    CASE WHEN COUNT(*) = SUM(CASE WHEN lrc_content IS NOT NULL THEN 1 ELSE 0 END) 
                         AND COUNT(*) > 0 THEN 1 ELSE 0 END,
                    CURRENT_TIMESTAMP
                FROM songs 
                WHERE album_id = OLD.album_id AND record_side = OLD.record_side;
            END;
        """)
        
        # 7. Populate songs table from existing tracklist data
        print("Migrating existing tracklist data to songs table...")
        
        cursor.execute("SELECT id, tracklist FROM albums WHERE tracklist IS NOT NULL AND tracklist != ''")
        albums_with_tracklist = cursor.fetchall()
        
        for album_id, tracklist_json in albums_with_tracklist:
            try:
                if tracklist_json:
                    tracklist = json.loads(tracklist_json)
                    if isinstance(tracklist, list):
                        for i, track in enumerate(tracklist, 1):
                            if isinstance(track, dict):
                                title = track.get('title', f'Track {i}')
                                duration = track.get('duration', '')
                                
                                # Try to parse duration to seconds
                                duration_seconds = None
                                if duration and isinstance(duration, str):
                                    try:
                                        if ':' in duration:
                                            parts = duration.split(':')
                                            if len(parts) == 2:
                                                minutes, seconds = parts
                                                duration_seconds = int(minutes) * 60 + float(seconds)
                                    except:
                                        pass
                                
                                # Determine record side based on position (simple heuristic)
                                # Assume tracks 1-10 are A-side, 11+ are B-side
                                record_side = 'A' if i <= 10 else 'B'
                                
                                cursor.execute("""
                                    INSERT OR IGNORE INTO songs 
                                    (album_id, track_position, title, duration_seconds, record_side)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (album_id, i, title, duration_seconds, record_side))
            except json.JSONDecodeError:
                print(f"Warning: Could not parse tracklist for album {album_id}")
                continue
        
        # Commit all changes
        conn.commit()
        print("Migration completed successfully!")
        print("\nNew database structure:")
        print("- settings: Global configuration including default song buffer")
        print("- albums: Added song_buffer_seconds, combined_lrc_* columns")
        print("- songs: Individual song LRC files and buffer settings")
        print("- record_sides: Track completion status for each side")
        print("- Triggers: Automatically maintain record side completion status")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()