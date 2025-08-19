#!/usr/bin/env python3
"""
VinylVault startup script
"""

import os
import sys
from pathlib import Path

# Add the project directory to the Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from app import app
from init_db import init_database
from config import Config

def main():
    """Main startup function."""
    print("Starting VinylVault...")
    
    # Initialize database if it doesn't exist
    if not Config.DATABASE_PATH.exists():
        print("Initializing database...")
        init_database()
    
    # Set environment variables for development
    if 'FLASK_ENV' not in os.environ:
        os.environ['FLASK_ENV'] = 'development'
    
    # Run the Flask application
    print(f"Database: {Config.DATABASE_PATH}")
    print(f"Cache directory: {Config.CACHE_DIR}")
    print(f"Starting server on http://0.0.0.0:5000")
    print("Press Ctrl+C to stop")
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development'
    )

if __name__ == '__main__':
    main()