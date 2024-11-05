import json
import sqlite3
from datetime import datetime

# Database and output file paths
DB_PATH = 'video_data.db'
OUTPUT_JSON_PATH = 'latest_sermons.json'

def get_latest_sermons():
    # Connect to the SQLite database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query to select required fields, filter by non-null summary_link, and sort by date descending
    query = """
        SELECT video_id, date, summary_link, thumbnail_url, name
        FROM videos
        WHERE summary_link IS NOT NULL
        ORDER BY date DESC
    """
    cursor.execute(query)
    
    # Fetch all the results
    sermons = []
    for row in cursor.fetchall():
        video_id, date, summary_link, thumbnail_url, name = row

        # Query to fetch tags for the current video_id
        cursor.execute("SELECT tag FROM video_tags WHERE video_id = ?", (video_id,))
        tags = [tag_row[0] for tag_row in cursor.fetchall()]
        
        sermons.append({
            'video_id': video_id,
            'date': date,
            'summary_link': summary_link + '/video.html',
            'thumbnail_url': thumbnail_url,
            'title': name,
            'tags': tags
        })
    
    # Close the database connection
    conn.close()
    
    return sermons

def write_to_json(data):
    # Write data to JSON file
    with open(OUTPUT_JSON_PATH, 'w') as json_file:
        json.dump(data, json_file, indent=4)

# Main function to fetch data and write to JSON
def update_latest_sermons_json():
    latest_sermons = get_latest_sermons()
    write_to_json(latest_sermons)
    print(f"latest_sermons.json has been updated with {len(latest_sermons)} sermons.")

# Run the function to update the JSON file
update_latest_sermons_json()
