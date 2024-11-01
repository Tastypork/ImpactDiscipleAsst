import sqlite3
import requests
import yaml
import isodate
import time
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

CONFIG_FILE = 'data/config.yml'

with open(CONFIG_FILE) as config_file:
            config = yaml.safe_load(config_file)
API_KEY = config['token'] # API Key
CHANNEL_ID = 'UCuKhKyFSA0esUpF09nM9OSA'  # Impact Church Channel ID
PLAYLIST_ID = 'UUuKhKyFSA0esUpF09nM9OSA'  # Impact Church Videos ID

def log_new_video(video_id):
    conn = sqlite3.connect('data/video_data.db')
    cursor = conn.cursor()

    # Get video details
    details = get_video_details(video_id)

    if not details:
        print(f"Failed to retrieve details for video: {video_id}")
    
    # Insert the new video into the database
    cursor.execute('''
        INSERT OR REPLACE INTO videos (
            video_id, date, name, speaker, church, duration, description, video_link, summary_link, transcript
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        video_id,
        details['date'],
        details['name'],
        details['speaker'],
        details['church'],
        details['duration'],
        details['description'],
        details['video_link'],
        details['summary_link'], #TODO -> Summary & text generation
        details['transcript']  
    ))

    conn.commit()
    conn.close()
    print(f"Logged new video: {video_id}")

def get_video_details(video_id):
    """Fetch video details from YouTube API."""
    url = 'https://www.googleapis.com/youtube/v3/videos'
    params = {
        'part': 'snippet,contentDetails',
        'id': video_id,
        'key': API_KEY
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        video_data = response.json().get('items', [])[0]
        
        # Extract fields
        snippet = video_data['snippet']
        content_details = video_data['contentDetails']
        
        title = snippet['title']
        date = snippet['publishedAt']
        description = snippet['description']
        duration = isodate.parse_duration(content_details['duration'])
        
        # Split the title based on '|' delimiters
        title_parts = title.split('|')
        if len(title_parts) == 3 and '#shorts' != title.lower()[:7]:
            name, speaker, church = [part.strip() for part in title_parts]
        else:
            name, speaker, church = title, "Unknown", "Unknown"
        
        # Retrieve the transcript if available
        transcript = get_transcript(video_id)

        # Construct the YouTube link from the video ID
        video_link = f'https://www.youtube.com/watch?v={video_id}'

        return {
            'video_id': video_id,
            'video_link': video_link,
            'date': date,
            'name': name,
            'speaker': speaker,
            'church': church,
            'duration': duration,
            'description': description,
            'summary_link': None,
            'transcript': transcript
        }
    else:
        print(f"Failed to get video details for ID {video_id}")
        return None

# retrieve transcript data
def get_transcript(video_id):
    print(f"Attempting to retrieve transcript for video ID: {video_id}")
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Fetch the transcript as a list of caption objects
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            if not transcript_data:
                print(f"No transcript data found for video ID: {video_id}")
                return None
            
            # Join all caption texts into a single string
            transcript_text = " ".join([item['text'] for item in transcript_data])
            print(f"Successfully retrieved transcript for video ID: {video_id}")
            return transcript_text
        
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            print(f"Transcript not available for video ID {video_id}: {e}")
            return None  # These errors should not be retried

        except Exception as e:
            retry_count += 1
            print(f"Unexpected error for video ID {video_id}: {e}")
            if retry_count < max_retries:
                print(f"Retrying... ({retry_count}/{max_retries})")
                time.sleep(2)  # Wait a moment before retrying
            else:
                print(f"Failed to retrieve transcript for video ID {video_id} after {max_retries} attempts.")
                return None