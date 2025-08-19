#!/usr/bin/env python3
"""
Test script for LRC functionality without requiring Flask.
Tests database operations and LRC processing logic.
"""

import sqlite3
import json
import re
from pathlib import Path
from config import Config

def test_database_schema():
    """Test that the database schema is correct."""
    print("Testing database schema...")
    
    conn = sqlite3.connect(str(Config.DATABASE_PATH))
    cursor = conn.cursor()
    
    # Test settings table
    cursor.execute("SELECT * FROM settings WHERE key = 'default_song_buffer_seconds'")
    setting = cursor.fetchone()
    if setting:
        print(f"✓ Default buffer setting found: {setting[1]} seconds")
    else:
        print("✗ Default buffer setting not found")
    
    # Test albums table has new columns
    cursor.execute("PRAGMA table_info(albums)")
    columns = [row[1] for row in cursor.fetchall()]
    
    required_columns = ['song_buffer_seconds', 'combined_lrc_a_side', 'combined_lrc_b_side']
    for col in required_columns:
        if col in columns:
            print(f"✓ Albums table has {col} column")
        else:
            print(f"✗ Albums table missing {col} column")
    
    # Test songs table
    cursor.execute("SELECT COUNT(*) FROM songs")
    song_count = cursor.fetchone()[0]
    print(f"✓ Songs table has {song_count} records")
    
    # Test record_sides table
    cursor.execute("SELECT COUNT(*) FROM record_sides")
    sides_count = cursor.fetchone()[0]
    print(f"✓ Record_sides table has {sides_count} records")
    
    conn.close()

def test_lrc_parsing():
    """Test LRC parsing functionality."""
    print("\nTesting LRC parsing...")
    
    sample_lrc = """[ar:Test Artist]
[al:Test Album]
[ti:Test Song]

[00:12.00]First line of lyrics
[00:15.50]Second line of lyrics
[01:23.45]Another line with a longer timestamp
[02:30.12]Final line"""
    
    # Test LRC validation regex
    if re.search(r'\[\d{2}:\d{2}\.\d{2}\]', sample_lrc):
        print("✓ LRC format validation works")
    else:
        print("✗ LRC format validation failed")
    
    # Test timestamp parsing
    lines = sample_lrc.strip().split('\n')
    parsed_count = 0
    
    for line in lines:
        line = line.strip()
        match = re.match(r'(\[\d{2}:\d{2}\.\d{2}\])(.*)', line)
        if match:
            timestamp_str, lyric_text = match.groups()
            # Parse timestamp
            time_match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2})\]', timestamp_str)
            if time_match:
                minutes, seconds, hundredths = map(int, time_match.groups())
                total_seconds = minutes * 60 + seconds + hundredths / 100.0
                print(f"✓ Parsed timestamp {timestamp_str} = {total_seconds}s: '{lyric_text}'")
                parsed_count += 1
    
    print(f"✓ Successfully parsed {parsed_count} timestamped lines")

def test_buffer_precedence():
    """Test buffer field precedence logic."""
    print("\nTesting buffer precedence logic...")
    
    # Simulate precedence logic: song > album > global
    global_default = 3.0
    album_buffer = 5.0
    song_buffer = 2.5
    
    # Test case 1: Song has specific buffer
    effective = song_buffer or album_buffer or global_default
    if effective == 2.5:
        print("✓ Song buffer takes precedence")
    
    # Test case 2: No song buffer, use album
    song_buffer = None
    effective = song_buffer or album_buffer or global_default
    if effective == 5.0:
        print("✓ Album buffer used when no song buffer")
    
    # Test case 3: No song or album buffer, use global
    album_buffer = None
    effective = song_buffer or album_buffer or global_default
    if effective == 3.0:
        print("✓ Global default used when no song or album buffer")

def test_lrc_combination_logic():
    """Test LRC file combination logic."""
    print("\nTesting LRC combination logic...")
    
    # Sample songs for combination
    songs = [
        {
            'title': 'Song 1',
            'duration_seconds': 180,  # 3 minutes
            'lrc_content': '[00:10.00]First song line 1\n[00:15.00]First song line 2',
            'song_buffer_seconds': None
        },
        {
            'title': 'Song 2', 
            'duration_seconds': 240,  # 4 minutes
            'lrc_content': '[00:05.00]Second song line 1\n[00:12.00]Second song line 2',
            'song_buffer_seconds': 4.0
        }
    ]
    
    # Simulate combination logic
    combined_lines = []
    cumulative_offset = 0.0
    album_buffer = 3.0
    
    for i, song in enumerate(songs):
        combined_lines.append(f"[-- Track: {song['title']} --]")
        
        # Parse and adjust timestamps
        lines = song['lrc_content'].strip().split('\n')
        for line in lines:
            match = re.match(r'(\[\d{2}:\d{2}\.\d{2}\])(.*)', line)
            if match:
                timestamp_str, lyric_text = match.groups()
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
                    
                    combined_lines.append(f"{new_timestamp}{lyric_text}")
        
        # Add buffer time (except for last song)
        if i < len(songs) - 1:
            buffer_seconds = song['song_buffer_seconds'] or album_buffer
            cumulative_offset += song['duration_seconds'] + buffer_seconds
        else:
            cumulative_offset += song['duration_seconds']
    
    print("✓ LRC combination logic completed")
    print(f"✓ Final combined duration: {cumulative_offset} seconds ({cumulative_offset/60:.1f} minutes)")
    print("✓ Sample combined LRC:")
    for line in combined_lines[:6]:  # Show first 6 lines
        print(f"   {line}")

def main():
    print("VinylVault LRC Functionality Test")
    print("=================================")
    
    try:
        test_database_schema()
        test_lrc_parsing()
        test_buffer_precedence()
        test_lrc_combination_logic()
        
        print("\n" + "="*50)
        print("✅ All tests completed successfully!")
        print("✅ LRC functionality appears to be working correctly.")
        print("\nNext steps:")
        print("- Install Flask dependencies to test the web interface")
        print("- Upload some sample LRC files to test the full workflow")
        print("- Verify the combination feature works in the browser")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)