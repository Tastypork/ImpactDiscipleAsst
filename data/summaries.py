import os
import sqlite3
import shutil
import requests
import yaml
from datetime import datetime

CONFIG_FILE = 'config.yml'

with open(CONFIG_FILE) as config_file:
            config = yaml.safe_load(config_file)

# Database and directory paths
DATABASE_PATH = 'video_data.db'
SERMONS_DIR = '../html/sermons'
TEMPLATE_DIR = '../html/template'

# Connect to the SQLite database
def connect_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Enable access to columns by name
    return conn

# Function to create a new directory and copy template files
def setup_video_directory(video_id, date):
    # Format date as YYYY-MM-DD for folder naming
    date_prefix = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    new_dir_name = f"{date_prefix}_{video_id}"
    new_dir = os.path.join(SERMONS_DIR, new_dir_name)
    
    # Create the directory if it doesn't exist
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)
    else:
        return
    
    # Copy files from the template directory
    for filename in ['video.html', 'video.js', 'config.json']:
        src_path = os.path.join(TEMPLATE_DIR, filename)
        dst_path = os.path.join(new_dir, filename)
        shutil.copy2(src_path, dst_path)

# Update the summary link in the database
def update_summary_link(conn, video_id):
    summary_link = f"../html/sermons/{video_id}"
    with conn:
        conn.execute(
            "UPDATE videos SET summary_link = ? WHERE video_id = ?",
            (summary_link, video_id)
        )

# Prepare and send an API call to Claude AI
def send_to_claude(video_title, video_speaker, video_transcript):
    # Define your API endpoint and headers here
    CLAUDE_API_URL = 'https://api.anthropic.com/v1/claude'  # Example endpoint
    API_KEY = config['claude_token']
    
    headers = {
        'speakerization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    # Define the payload with your custom prompt
    prompt = f"Provide an in-depth summary and analysis for the following video titled '{video_title}': {video_transcript}"
    data = {
        'model': 'claude-v1',  # Specify the model if needed
        'prompt': prompt,
        'max_tokens_to_sample': 300  # Adjust as necessary
    }

    # Make the API request
    response = requests.post(CLAUDE_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        return response.json().get("text")  # Adjust based on actual API response format
    else:
        print(f"Error with Claude API request: {response.status_code} - {response.text}")
        return None

# Main function to process videos
def process_videos():
    conn = connect_db()
    cursor = conn.cursor()

    # Query videos with an speaker
    cursor.execute("SELECT video_id, title, description FROM videos WHERE speaker IS NOT NULL")
    videos = cursor.fetchall()

    for video in videos:
        video_id = video['video_id']
        video_date = video['date']
        
        # Create directory and copy files
        setup_video_directory(video_id, video_date)
        
        # Update summary_link in the database
        update_summary_link(conn, video_id)
        
        # Make API call to Claude for additional processing
        video_title = video['title']
        video_speaker= video['speaker']
        video_transcript = video['transcription']
        api_response = send_to_claude(video_title, video_speaker, video_transcript)

        
        
        

    conn.close()

# Run the process
if __name__ == "__main__":
    process_videos()
