# Album-Side LRC File Generator

This document provides a script and a methodology for fetching individual LRC lyric files for all tracks on an album, concatenating them, and adjusting their timestamps to create a single, continuous LRC file for an entire album side. This is useful for "gapless" albums where songs flow directly into one another.

The process relies on the **LRCLIB API** and a **Python script** to automate the fetching and timestamp calculations.

---

## ## Prerequisites

Before you begin, ensure you have the following installed:

1.  **Python 3**: The script is written in Python.
2.  **Requests Library**: A Python library for making HTTP requests. You can install it via pip:
    ```bash
    pip install requests
    ```

---

## ## The Python Script

Save the following code as a Python file (e.g., `lrc_stitcher.py`). The script is designed to be configured by editing the `album_tracks` list directly within the file.

```python
import requests
import re
import time

# --- Configuration ---
# Define the album, artist, and tracklist.
# IMPORTANT: The 'duration_seconds' for each track must be accurate.
# This value is used to calculate the time offset for the subsequent track.
# The final track's duration is not strictly necessary but is good practice.

ALBUM_CONFIG = {
    "artist_name": "Pink Floyd",
    "album_name": "The Dark Side of the Moon",
    "output_filename": "dark_side_of_the_moon_A_side.lrc",
    "tracks": [
        {"track_name": "Speak to Me / Breathe", "duration_seconds": 238},
        {"track_name": "On the Run", "duration_seconds": 213},
        {"track_name": "Time", "duration_seconds": 413},
        {"track_name": "The Great Gig in the Sky", "duration_seconds": 283},
    ]
}

# LRCLIB API endpoint
API_URL = "[https://lrclib.net/api/get-cached](https://lrclib.net/api/get-cached)"

def parse_lrc_time(timestamp):
    """Converts LRC timestamp [mm:ss.xx] to total seconds."""
    match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2})\]', timestamp)
    if not match:
        return None
    minutes, seconds, hundredths = map(int, match.groups())
    return minutes * 60 + seconds + hundredths / 100.0

def format_lrc_time(total_seconds):
    """Converts total seconds back to LRC timestamp [mm:ss.xx]."""
    if total_seconds < 0:
        total_seconds = 0
    minutes = int(total_seconds / 60)
    seconds = int(total_seconds % 60)
    hundredths = int((total_seconds - int(total_seconds)) * 100)
    return f"[{minutes:02d}:{seconds:02d}.{hundredths:02d}]"

def process_album(config):
    """Fetches, merges, and retimes LRC files for the configured album."""
    cumulative_offset = 0.0
    full_lrc_lines = []
    
    # Add some metadata to the top of the file
    full_lrc_lines.append(f"[ar:{config['artist_name']}]")
    full_lrc_lines.append(f"[al:{config['album_name']} (Stitched)]")
    full_lrc_lines.append(f"[ti:Full Album Side]")
    full_lrc_lines.append("")

    for track in config["tracks"]:
        print(f"Fetching lyrics for: '{track['track_name']}'...")

        params = {
            "artist_name": config["artist_name"],
            "album_name": config["album_name"],
            "track_name": track["track_name"],
        }

        try:
            response = requests.get(API_URL, params=params, timeout=10)
            response.raise_for_status() # Raises an exception for bad status codes
        except requests.exceptions.RequestException as e:
            print(f"  -> ERROR: Network or API error for '{track['track_name']}'. Skipping. Error: {e}")
            cumulative_offset += track["duration_seconds"]
            continue

        if response.status_code == 200 and response.text:
            print(f"  -> Found. Processing and adding offset of {cumulative_offset:.2f} seconds.")
            
            # Add a non-timed tag to indicate the start of a new track
            full_lrc_lines.append(f"[-- Track: {track['track_name']} --]")

            lines = response.text.strip().split('\n')
            for line in lines:
                line = line.strip()
                match = re.match(r'(\[\d{2}:\d{2}\.\d{2}\])(.*)', line)
                if match:
                    timestamp_str, lyric_text = match.groups()
                    original_seconds = parse_lrc_time(timestamp_str)
                    if original_seconds is not None:
                        new_seconds = original_seconds + cumulative_offset
                        new_timestamp = format_lrc_time(new_seconds)
                        full_lrc_lines.append(f"{new_timestamp}{lyric_text}")
                # Keep metadata or non-timed lines (like the track indicator above)
                elif not re.match(r'\[(ar|al|ti|au|length|by|offset):.*\]', line):
                     full_lrc_lines.append(line)


            # Add the current track's duration to the offset for the next track
            cumulative_offset += track["duration_seconds"]
        else:
            print(f"  -> Not found in LRCLIB cache. Skipping.")
            # Still add the duration to keep subsequent timings correct
            cumulative_offset += track["duration_seconds"]
        
        # A small delay to be polite to the API
        time.sleep(1)

    print(f"\nWriting combined LRC to '{config['output_filename']}'...")
    with open(config['output_filename'], 'w', encoding='utf-8') as f:
        for line in full_lrc_lines:
            f.write(line + '\n')
    print("Done.")


if __name__ == "__main__":
    process_album(ALBUM_CONFIG)
