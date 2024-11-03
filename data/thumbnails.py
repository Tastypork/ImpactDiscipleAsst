import sqlite3
import requests
import yaml

# Load the API key from your configuration
CONFIG_FILE = 'config.yml'
with open(CONFIG_FILE) as config_file:
    config = yaml.safe_load(config_file)
API_KEY = config['yt_token']

def get_thumbnail_url(video_id):
    """Fetch the thumbnail URL for a given video ID from YouTube API."""
    url = 'https://www.googleapis.com/youtube/v3/videos'
    params = {
        'part': 'snippet',
        'id': video_id,
        'key': API_KEY
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        video_data = response.json().get('items', [])[0]
        # Try to get the highest resolution thumbnail available
        thumbnails = video_data['snippet']['thumbnails']
        if 'maxres' in thumbnails:
            thumbnail_url = thumbnails['maxres']['url']
        elif 'standard' in thumbnails:
            thumbnail_url = thumbnails['standard']['url']
        elif 'high' in thumbnails:
            thumbnail_url = thumbnails['high']['url']
        elif 'medium' in thumbnails:
            thumbnail_url = thumbnails['medium']['url']
        else:
            thumbnail_url = thumbnails['default']['url']
        return thumbnail_url
    else:
        print(f"Failed to get thumbnail for video ID {video_id}")
        return None


# Path to your SQLite database
database_path = 'video_data.db'

# Connect to the database
conn = sqlite3.connect(database_path)
cursor = conn.cursor()

 # Check if the column already exists in the table schema
cursor.execute(f"PRAGMA table_info('videos')")
columns = [column[1] for column in cursor.fetchall()]

# Add a new column for thumbnail URLs
if 'thumbnail_url' not in columns:
    cursor.execute("ALTER TABLE videos ADD COLUMN thumbnail_url TEXT")

# Fetch all video IDs from the database
cursor.execute("SELECT video_id FROM videos")
video_ids = cursor.fetchall()

# Update each video with its thumbnail URL
for (video_id,) in video_ids:
    thumbnail_url = get_thumbnail_url(video_id)
    if thumbnail_url:
        cursor.execute("UPDATE videos SET thumbnail_url = ? WHERE video_id = ?", (thumbnail_url, video_id))

# Commit the changes and close the connection
conn.commit()
conn.close()

print("Added thumbnail_url column to the videos table.")
