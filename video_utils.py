import os
import sqlite3
import shutil
import requests
import yaml
import isodate
import re
import time
import anthropic
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

CONFIG_FILE = 'data/config.yml'

with open(CONFIG_FILE) as config_file:
            config = yaml.safe_load(config_file)

YT_KEY = config['yt_token'] # Youtube API Key
CLAUDE_KEY = config['claude_token'] # Claude API Key
# Database and directory paths
DATABASE_PATH = 'data/video_data.db'
SERMONS_DIR = 'html/sermons'
TEMPLATE_DIR = 'html/sermons/template'
OUTPUT_JSON_PATH = 'html/latest_sermons.json'

def log_new_video(video_id):
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get video details from YT API
    details = get_video_details(video_id)
    details = {key: value.replace('"', "'") if isinstance(value, str) else value for key, value in details.items()}

    if not details:
        print(f"Failed to retrieve details for video: {video_id}")
        return None
    
    # Insert the new video into the database
    cursor.execute('''
        INSERT OR REPLACE INTO videos (
            video_id, date, name, speaker, church, duration, description, video_link, summary_link, transcript, thumbnail_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        video_id,
        details['date'],
        details['name'],
        details['speaker'],
        details['church'],
        details['duration'],
        details['description'],
        details['video_link'],
        details['summary_link'],
        details['transcript'],
        details['thumbnail_url']  
    ))
    conn.commit()

    # Create directory and copy files
    new_dir = setup_video_directory(video_id, details['date'])
    config_dst = os.path.join(new_dir, 'config.json')
    error_dst = os.path.join(new_dir, 'error.txt')

    print(f"Requesting data for {video_id}")
    api_response = send_to_claude(details['speaker'], details['transcript'], error_dst)

    if api_response:
        json_data_match = re.search(r'\{.*\}', api_response[0].text, re.DOTALL)
        if json_data_match:
            json_data = json_data_match.group()  # Get the JSON data as a string
            try:
                # Parse JSON to check for valid structure
                json_data_dict = json.loads(json_data)
                json_data_dict['videoUrl'] = f"https://www.youtube.com/embed/{video_id}"
                
                # Write parsed JSON data to a file
                with open(config_dst, 'w') as json_file:
                    json.dump(json_data_dict, json_file, indent=4)
                
                print(f"JSON data has been written to config.json for {video_id}")
            except json.JSONDecodeError:
                print(f"Invalid JSON format for {video_id}. Written to {error_dst}")
                with open(error_dst, "w") as file:
                    file.write(api_response[0].text)
                cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
                return None
        else:
            print(f"Failed to match JSON data for video_id {video_id}")
            cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
            return None
    else:
        print(f"Claude content was not created sucessfully for video_id {video_id}")
        cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
        return None
    
    tags = insert_video_tags(config_dst, video_id)

    update_json(video_id, details['date'], details['summary_link'], details['thumbnail_url'], details['name'], tags)

    conn.close()
    return 1

def get_video_details(video_id):
    """Fetch video details from YouTube API."""
    url = 'https://www.googleapis.com/youtube/v3/videos'
    params = {
        'part': 'snippet,contentDetails',
        'id': video_id,
        'key': YT_KEY
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        video_data = response.json().get('items', [])[0]
        
        # Extract fields
        snippet = video_data['snippet']
        content_details = video_data['contentDetails']
        
        title = snippet['title']
        date = datetime.fromisoformat(snippet['publishedAt'][:-1]).strftime('%Y-%m-%d')
        description = snippet['description']
        duration = str(isodate.parse_duration(content_details['duration']))
        date_prefix = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
        new_dir_name = f"{date_prefix}_{video_id}"
        summary_link = f"../html/sermons/{new_dir_name}"
        
        # Try to get the highest resolution thumbnail available
        thumbnails = snippet['thumbnails']
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
        
        # Split the title based on '|' delimiters
        title_parts = title.split('|')
        if len(title_parts) == 3 and '#shorts' != title.lower()[:7]:
            name, speaker, church = [part.strip() for part in title_parts]
        else:
            name, speaker, church = title, "Unknown", "Unknown"
        
        # Retrieve the transcript if available
        transcript = get_transcript(video_id)

        # Construct the YouTube link from the video ID
        video_link = f'https://www.youtube.com/embed/{video_id}'

        return {
            'video_id': video_id,
            'video_link': video_link,
            'date': date,
            'name': name,
            'speaker': speaker,
            'church': church,
            'duration': duration,
            'description': description,
            'summary_link': summary_link,
            'transcript': transcript,
            'thumbnail_url': thumbnail_url
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

# Function to create a new directory and copy template files
def setup_video_directory(video_id, date):
    # Format date as YYYY-MM-DD for folder naming
    date_prefix = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    new_dir_name = f"{date_prefix}_{video_id}"
    new_dir = os.path.join(SERMONS_DIR, new_dir_name)
    
    summary_link = f"sermons/{new_dir_name}"
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute(
            "UPDATE videos SET summary_link = ? WHERE video_id = ?",
            (summary_link, video_id)
        )
    conn.close()
        
    # Create the directory if it doesn't exist
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)
    else:
        print('Folder exists, skipping initial directory setup')
        return new_dir
    
    # Copy files from the template directory
    for filename in ['video.html', 'video.js']:
        src_path = os.path.join(TEMPLATE_DIR, filename)
        dst_path = os.path.join(new_dir, filename)
        shutil.copy2(src_path, dst_path)

    return new_dir

# Prepare and send an API call to Claude AI
def send_to_claude(video_speaker, video_transcript, error_dst):
    # Define your API endpoint and headers here
    client = anthropic.Anthropic(api_key=config['claude_token'])

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tag FROM tags")
    tags = cursor.fetchall()
    conn.close()

    # Load the JSON data
    with open('data/message_data_haiku.json', 'r') as f:
        message_data = json.load(f)

    SERMON_TRANSCRIPT = video_transcript
    SPEAKER = video_speaker
    TAGS = [row[0] for row in tags]
    TAGS_LIST = ' || '.join(f'{tag}' for tag in TAGS)

    message_data_str = json.dumps(message_data)  # Convert JSON to string for replacement
    message_data_str = message_data_str.replace("{{SERMON_TRANSCRIPT}}", SERMON_TRANSCRIPT)
    message_data_str = message_data_str.replace("{{SPEAKER}}", SPEAKER)
    message_data_str = message_data_str.replace("{{TAGS_LIST}}", TAGS_LIST)

    try:
        # Convert back to dictionary
        message_data = json.loads(message_data_str)
    except json.JSONDecodeError:
        print(f"Invalid JSON format after variable substition. Written to {error_dst}")
        with open(error_dst, "w") as file:
            file.write(message_data_str)
        return None

    try:
        # Attempt to create the message with the provided data
        message = client.messages.create(**message_data)
    except Exception as e:
        # Catch any error that occurs and print a message
        print("An error occurred while creating the message:", str(e))
        if 'Error code: 429' in str(e):
            exit()
        return None

    print(message.usage)

    return message.content

def insert_video_tags(config_path, video_id):
    # Extract video_id from folder name (assuming folder name format: date_video_id)
    folder_name = os.path.basename(os.path.dirname(config_path))

    # Connect to the database
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Load tags from config.json
    try:
        with open(config_path, 'r') as config_file:
            config_data = json.load(config_file)
        tags = config_data['tags']  # Direct access if 'tags' always exists
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error reading tags from {config_path}: {e}")
        conn.close()
        return

    # Insert each tag into the database
    for tag in tags:
        try:
            cursor.execute("""
            INSERT INTO video_tags (video_id, tag)
            VALUES (?, ?)
            """, (video_id, tag))
        except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    print(f"Skipped duplicate entry: video_id={video_id}, tag={tag}")
                else:
                    print(f"An unexpected error occurred: {e}")
                    raise  # Re-raise any other exceptions
    
    conn.commit()
    conn.close()

    return tags

def update_json(video_id, date, summary_link, thumbnail_url, name, tags):
    sermons = []
    sermons.append({
            'video_id': video_id,
            'date': date,
            'summary_link': summary_link + '/video.html',
            'thumbnail_url': thumbnail_url,
            'title': name,
            'tags': tags
        })
    
    # Read the existing JSON data from the file
    with open(OUTPUT_JSON_PATH, 'r') as file:
        existing_data = json.load(file)

    # Append to the beginning
    updated_data = [new_data] + existing_data

    # Write back to file
    with open(OUTPUT_JSON_PATH, 'w') as file:
        json.dump(updated_data, file, indent=4)
