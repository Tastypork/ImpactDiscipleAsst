import requests
import json
from datetime import datetime
import yaml
import isodate

CONFIG_FILE = 'config.yml'

with open(CONFIG_FILE) as config_file:
            config = yaml.safe_load(config_file)
API_KEY = config['yt_token'] # API Key
CHANNEL_ID = 'UCuKhKyFSA0esUpF09nM9OSA'  # Impact Church Channel ID
PLAYLIST_ID = 'UUuKhKyFSA0esUpF09nM9OSA'  # Impact Church Videos ID

def get_all_videos():
    """Retrieve all videos from a YouTube channel's uploads playlist."""
    videos = {}
    url = 'https://www.googleapis.com/youtube/v3/playlistItems'
    params = {
        'part': 'snippet',
        'maxResults': 50,  # YouTube API limit per request
        'playlistId': PLAYLIST_ID,
        'key': API_KEY
    }

    # Paginate through all videos in the playlist
    while True:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            for item in data.get('items', []):
                video_id = item['snippet']['resourceId']['videoId']
                title = item['snippet']['title']
                date = item['snippet']['publishedAt']
                description = item['snippet']['description']

                # Split the title based on '|' delimiters
                title_parts = title.split('|')
                if len(title_parts) == 3 and '#shorts' != title.lower()[:7]:
                    name, speaker, church = [part.strip() for part in title_parts]
                else:
                    name, speaker, church = title, "Unknown", "Unknown"

                # Fetch video details (duration) using the video ID
                video_details = get_video_details(video_id)

                # Store the video data in the dictionary
                videos[video_id] = {
                    'date': datetime.fromisoformat(date[:-1]).strftime('%Y-%m-%d'),
                    'name': name,
                    'speaker': speaker,
                    'church': church,
                    'description': description,
                    'duration': video_details.get('duration', 'Unknown')
                }
            
            # Check if there's a next page
            if 'nextPageToken' in data:
                params['pageToken'] = data['nextPageToken']
            else:
                break
        else:
            print("Failed to retrieve videos:", response.status_code, response.text)
            break
    return videos

# get video details from a different API ~ specifically for the duration
def get_video_details(video_id):
    """Retrieve additional details like video duration from the YouTube API."""
    url = 'https://www.googleapis.com/youtube/v3/videos'
    params = {
        'part': 'contentDetails',
        'id': video_id,
        'key': API_KEY
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        items = response.json().get('items', [])
        if items:
            duration = items[0]['contentDetails']['duration']
            return {
                'duration': convert_duration(duration)
            }
    return {}

# Helper function
def convert_duration(duration):
    """Convert ISO 8601 duration (e.g., PT1H2M3S) to a human-readable format."""
    parsed_duration = isodate.parse_duration(duration)
    return str(parsed_duration)

# retrieve the video data and store in a json
with open('data.json', 'w') as f:
    json.dump(get_all_videos(), f)
