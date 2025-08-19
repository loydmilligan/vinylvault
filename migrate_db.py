#!/usr/bin/env python3
"""
Database migration script for VinylVault.
Ensures database schema is compatible with the enhanced Discogs integration.
"""

import sqlite3
import logging
from pathlib import Path

from config import Config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_database_exists():
    """Check if database exists."""
    return Config.DATABASE_PATH.exists()

def get_schema_version(conn):
    """Get current schema version."""
    try:
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        result = cursor.fetchone()
        return result[0] if result else 0
    except sqlite3.OperationalError:
        # schema_version table doesn't exist
        return 0

def create_schema_version_table(conn):
    """Create schema version tracking table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)
    conn.commit()

def migration_v1_initial_schema(conn):
    """Migration v1: Initial schema (should already exist)."""
    logger.info("Migration v1: Verifying initial schema")
    
    # Check if all required tables exist
    cursor = conn.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN ('users', 'albums', 'sync_log', 'random_cache')
    """)
    existing_tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = ['users', 'albums', 'sync_log', 'random_cache']
    missing_tables = set(required_tables) - set(existing_tables)
    
    if missing_tables:
        logger.error(f"Missing required tables: {missing_tables}")
        logger.info("Please run init_db.py first to create the initial schema")
        return False
    
    # Record this migration
    conn.execute("""
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES (1, 'Initial schema verification')
    """)
    conn.commit()
    
    logger.info("✓ Initial schema verified")
    return True

def migration_v2_enhanced_sync_logging(conn):
    """Migration v2: Enhanced sync logging."""
    logger.info("Migration v2: Enhanced sync logging")
    
    # Add additional columns to sync_log if they don't exist
    try:
        # Check if columns exist
        cursor = conn.execute("PRAGMA table_info(sync_log)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add error_details column if it doesn't exist
        if 'error_details' not in columns:
            conn.execute("ALTER TABLE sync_log ADD COLUMN error_details TEXT")
            logger.info("✓ Added error_details column to sync_log")
        
        # Add sync_type column if it doesn't exist
        if 'sync_type' not in columns:
            conn.execute("ALTER TABLE sync_log ADD COLUMN sync_type TEXT DEFAULT 'manual'")
            logger.info("✓ Added sync_type column to sync_log")
        
        # Add duration_seconds column if it doesn't exist
        if 'duration_seconds' not in columns:
            conn.execute("ALTER TABLE sync_log ADD COLUMN duration_seconds INTEGER")
            logger.info("✓ Added duration_seconds column to sync_log")
        
    except sqlite3.Error as e:
        logger.error(f"Error in migration v2: {e}")
        return False
    
    # Record this migration
    conn.execute("""
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES (2, 'Enhanced sync logging columns')
    """)
    conn.commit()
    
    logger.info("✓ Enhanced sync logging migration completed")
    return True

def migration_v3_performance_indexes(conn):
    """Migration v3: Additional performance indexes."""
    logger.info("Migration v3: Performance indexes")
    
    # Additional indexes for better performance
    indexes = [
        ("idx_albums_title_search", "CREATE INDEX IF NOT EXISTS idx_albums_title_search ON albums (title COLLATE NOCASE)"),
        ("idx_albums_artist_year", "CREATE INDEX IF NOT EXISTS idx_albums_artist_year ON albums (artist, year)"),
        ("idx_albums_genres", "CREATE INDEX IF NOT EXISTS idx_albums_genres ON albums (genres)"),
        ("idx_albums_rating_year", "CREATE INDEX IF NOT EXISTS idx_albums_rating_year ON albums (rating, year)"),
        ("idx_sync_log_time", "CREATE INDEX IF NOT EXISTS idx_sync_log_time ON sync_log (sync_time DESC)"),
        ("idx_random_cache_served", "CREATE INDEX IF NOT EXISTS idx_random_cache_served ON random_cache (last_served)"),
    ]
    
    for index_name, index_sql in indexes:
        try:
            conn.execute(index_sql)
            logger.info(f"✓ Created index: {index_name}")
        except sqlite3.Error as e:
            logger.warning(f"Could not create index {index_name}: {e}")
    
    # Record this migration
    conn.execute("""
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES (3, 'Additional performance indexes')
    """)
    conn.commit()
    
    logger.info("✓ Performance indexes migration completed")
    return True

def migration_v4_discogs_metadata(conn):
    """Migration v4: Enhanced Discogs metadata support."""
    logger.info("Migration v4: Enhanced Discogs metadata")
    
    # Check if albums table has all required columns
    cursor = conn.execute("PRAGMA table_info(albums)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add missing columns for enhanced metadata
    new_columns = [
        ('country', 'TEXT'),
        ('format_details', 'TEXT'),  # JSON for format information
        ('label_info', 'TEXT'),      # JSON for label information
        ('barcode', 'TEXT'),
        ('catalog_number', 'TEXT'),
        ('master_id', 'INTEGER'),    # Discogs master release ID
        ('resource_url', 'TEXT'),    # Discogs API URL
        ('uri', 'TEXT'),             # Discogs web URL
        ('estimated_weight', 'INTEGER'),  # In grams
        ('condition', 'TEXT'),       # Record condition
        ('sleeve_condition', 'TEXT'), # Sleeve condition
    ]
    
    for column_name, column_type in new_columns:
        if column_name not in columns:
            try:
                conn.execute(f"ALTER TABLE albums ADD COLUMN {column_name} {column_type}")
                logger.info(f"✓ Added {column_name} column to albums")
            except sqlite3.Error as e:
                logger.warning(f"Could not add column {column_name}: {e}")
    
    # Record this migration
    conn.execute("""
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES (4, 'Enhanced Discogs metadata support')
    """)
    conn.commit()
    
    logger.info("✓ Enhanced Discogs metadata migration completed")
    return True

def migration_v5_wal_mode(conn):
    """Migration v5: Enable WAL mode for better concurrency."""
    logger.info("Migration v5: WAL mode configuration")
    
    try:
        # Check current journal mode
        cursor = conn.execute("PRAGMA journal_mode")
        current_mode = cursor.fetchone()[0]
        
        if current_mode.lower() != 'wal':
            # Enable WAL mode
            conn.execute("PRAGMA journal_mode=WAL")
            logger.info("✓ Enabled WAL mode")
        else:
            logger.info("✓ WAL mode already enabled")
        
        # Set other performance pragmas
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster than FULL, safer than OFF
        conn.execute("PRAGMA cache_size=10000")    # 10MB cache
        conn.execute("PRAGMA temp_store=MEMORY")   # Store temp tables in memory
        
        logger.info("✓ Performance pragmas configured")
        
    except sqlite3.Error as e:
        logger.warning(f"Could not configure WAL mode: {e}")
        return False
    
    # Record this migration
    conn.execute("""
        INSERT OR IGNORE INTO schema_version (version, description)
        VALUES (5, 'WAL mode and performance configuration')
    """)
    conn.commit()
    
    logger.info("✓ WAL mode migration completed")
    return True

def run_migrations():
    """Run all pending migrations."""
    if not check_database_exists():
        logger.error("Database does not exist. Please run init_db.py first.")
        return False
    
    # Connect to database
    conn = sqlite3.connect(str(Config.DATABASE_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    
    try:
        # Create schema version table if it doesn't exist
        create_schema_version_table(conn)
        
        # Get current schema version
        current_version = get_schema_version(conn)
        logger.info(f"Current schema version: {current_version}")
        
        # Define migrations in order
        migrations = [
            (1, migration_v1_initial_schema),
            (2, migration_v2_enhanced_sync_logging),
            (3, migration_v3_performance_indexes),
            (4, migration_v4_discogs_metadata),
            (5, migration_v5_wal_mode),
        ]
        
        # Run pending migrations
        success_count = 0
        for version, migration_func in migrations:
            if version > current_version:
                logger.info(f"Running migration v{version}")
                if migration_func(conn):
                    success_count += 1
                    logger.info(f"✓ Migration v{version} completed")
                else:
                    logger.error(f"❌ Migration v{version} failed")
                    break
            else:
                logger.debug(f"Skipping migration v{version} (already applied)")
        
        # Get final schema version
        final_version = get_schema_version(conn)
        logger.info(f"Final schema version: {final_version}")
        
        if final_version > current_version:
            logger.info(f"✅ Database migration completed! Applied {success_count} migrations.")
        else:
            logger.info("📋 Database schema is up to date.")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
    finally:
        conn.close()

def check_schema_integrity():
    """Check database schema integrity."""
    logger.info("Checking database schema integrity...")
    
    conn = sqlite3.connect(str(Config.DATABASE_PATH))
    
    try:
        # Check foreign key constraints
        conn.execute("PRAGMA foreign_key_check")
        logger.info("✓ Foreign key constraints are valid")
        
        # Check database integrity
        cursor = conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        if result == "ok":
            logger.info("✓ Database integrity check passed")
        else:
            logger.error(f"❌ Database integrity check failed: {result}")
            return False
        
        # Check that all required tables exist
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['albums', 'random_cache', 'schema_version', 'sync_log', 'users']
        missing_tables = set(required_tables) - set(tables)
        
        if missing_tables:
            logger.error(f"❌ Missing required tables: {missing_tables}")
            return False
        
        logger.info(f"✓ All required tables present: {', '.join(sorted(tables))}")
        
        # Check indexes
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_%'
            ORDER BY name
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        logger.info(f"✓ Found {len(indexes)} custom indexes")
        
        return True
        
    except Exception as e:
        logger.error(f"Schema integrity check failed: {e}")
        return False
    finally:
        conn.close()

def main():
    """Main migration function."""
    logger.info("🔧 VinylVault Database Migration Tool")
    logger.info("=" * 50)
    
    # Ensure cache directory exists
    Config.CACHE_DIR.mkdir(exist_ok=True)
    
    # Run migrations
    if run_migrations():
        # Check integrity
        if check_schema_integrity():
            logger.info("🎉 Database migration and integrity check completed successfully!")
            return True
        else:
            logger.error("❌ Integrity check failed after migration")
            return False
    else:
        logger.error("❌ Migration failed")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)