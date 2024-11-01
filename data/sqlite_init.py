import sqlite3
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

# Load JSON data from file
with open('data.json') as f:
    json_data = json.load(f)

# Connect to SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect('video_data.db')
cursor = conn.cursor()

tags_list = [
    "Faith", "Hope", "Love", "Forgiveness", "Salvation", "Prayer", 
    "Wisdom", "Peace", "Obedience", "Patience", "Identity", "Purpose", 
    "Healing", "Tithing", "Anger", "Relationships", "Suffering", "Joy", 
    "Temptation", "Sin", "Empathy", "Miracles", "Rest", "Sanctification", 
    "Leadership", "Blessings", "Gratitude"
]

# Create the tags table with a single column
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tags (   
        tag TEXT PRIMARY KEY
    )
''')

# Insert each tag into the database
for tag in tags_list:
    cursor.execute('INSERT OR IGNORE INTO tags (tag) VALUES (?)', (tag,))



# Create the junction table to link videos and tags
cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_tags (
        video_id TEXT,
        tag TEXT,
        PRIMARY KEY (video_id, tag),
        FOREIGN KEY (video_id) REFERENCES videos(video_id),
        FOREIGN KEY (tag) REFERENCES tags(tag)
    )
''')



# Create the main table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY,
        date TEXT,
        name TEXT,
        speaker TEXT,
        church TEXT,
        duration TEXT,
        description TEXT,
        video_link TEXT,
        summary_link TEXT,
        transcript TEXT
    )
''')

# Function to get the transcript text
def get_transcript(video_id):
    print(f"Attempting to retrieve transcript for video ID: {video_id}")
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
        return None
    except Exception as e:
        print(f"Unexpected error for video ID {video_id}: {e}")
        return None
    


# Insert JSON Data into the Database
for video_id, details in json_data.items():
    # Check if a transcript already exists for this video
    cursor.execute('SELECT transcript FROM videos WHERE video_id = ?', (video_id,))
    existing_transcript = cursor.fetchone()

    # Construct the YouTube link from the video ID
    video_link = f'https://www.youtube.com/watch?v={video_id}'
    
    # Retrieve the transcript
    if not existing_transcript or existing_transcript[0] is None:
        print(f"\n\nNo existing transcript for video ID {video_link}. Retrieving...")
        transcript = get_transcript(video_id)
    else:
        continue

    cursor.execute('''
        INSERT OR REPLACE INTO videos (
            video_id, date, name, speaker, church, duration, description, video_link, summary_link, transcript
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        video_id,
        details.get('date'),
        details.get('name'),
        details.get('speaker'),
        details.get('church'),
        details.get('duration'),
        details.get('description'),
        video_link,
        None,       # Placeholder for summary_link to be populated later
        transcript  # Store the transcript in the database
    ))

# Commit and close
conn.commit()
conn.close()
