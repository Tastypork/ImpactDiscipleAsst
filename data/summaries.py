import os
import sqlite3
import shutil
import yaml
from datetime import datetime
import anthropic
import json
import re
import time

CONFIG_FILE = 'config.yml'

with open(CONFIG_FILE) as config_file:
            config = yaml.safe_load(config_file)

# Database and directory paths
DATABASE_PATH = 'video_data.db'
SERMONS_DIR = '../html/sermons'
TEMPLATE_DIR = '../html/sermons/template'

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
    
    summary_link = f"../html/sermons/{new_dir_name}"
    with conn:
        conn.execute(
            "UPDATE videos SET summary_link = ? WHERE video_id = ?",
            (summary_link, video_id)
        )
    
    # Create the directory if it doesn't exist
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)
    else:
        return
    
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
    with open('message_data_haiku.json', 'r') as f:
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
        print(f"Invalid JSON format after variable substition")
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

def insert_video_tags(config_path, video_id, db_path='video_data.db'):
    # Extract video_id from folder name (assuming folder name format: date_video_id)
    folder_name = os.path.basename(os.path.dirname(config_path))

    # Connect to the database
    conn = sqlite3.connect(db_path)
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
        cursor.execute("""
        INSERT INTO video_tags (video_id, tag)
        VALUES (?, ?)
        """, (video_id, tag))
    
    conn.commit()
    conn.close()

# Main function to process videos
def process_videos():
    conn = connect_db()
    cursor = conn.cursor()

    # Query videos with an speaker
    cursor.execute("SELECT video_id, date, transcript, speaker FROM videos WHERE speaker IS NOT NULL AND summary_link IS NULL AND transcript IS NOT NULL")
    videos = cursor.fetchall()

    for video in videos:
        video_id = video['video_id']
        video_date = video['date']
        
        # Create directory and copy files
        new_dir = setup_video_directory(video_id, video_date)
        config_dst = os.path.join(new_dir, 'config.json')
        error_dst = os.path.join(new_dir, 'error.txt')
        
        # Make API call to Claude for additional processing
        video_speaker= video['speaker']
        video_transcript = video['transcript']

        print(f"Requesting data for {video_id}")
        time.sleep(30) # Optional sleep for rate limiting
        api_response = send_to_claude(video_speaker, video_transcript, error_dst)
        insert_video_tags(config_dst, video_id)

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
                    print(f"Invalid JSON format for {video_id}")
                    with open(error_dst, "w") as file:
                        file.write(api_response[0].text)
                    cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
            else:
                print(f"Failed to match JSON data for video_id {video_id}")
                cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
        else:
            print(f"Claude content was not created sucessfully for video_id {video_id}")
            cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
        
    conn.close()

# Run the process
if __name__ == "__main__":
    process_videos()
