import os
import sqlite3

# Path to the main directory containing the folders
directory_path = "../html/sermons"

# SQLite database connection
conn = sqlite3.connect('video_data.db')
cursor = conn.cursor()

def get_video_id_from_folder(folder_name):
    # Extract the video_id from the folder name (format: date_videoid)
    return folder_name.split('_', 1)[1] if '_' in folder_name else None

def remove_summary_link(video_id):
    try:
        cursor.execute("UPDATE videos SET summary_link = NULL WHERE video_id = ?", (video_id,))
        conn.commit()
        print(f"Removed summary link for video_id: {video_id}")
    except sqlite3.Error as e:
        print(f"Error removing summary link for video_id {video_id}: {e}")

# Main loop through folders
for folder in os.listdir(directory_path):
    folder_path = os.path.join(directory_path, folder)
    if os.path.isdir(folder_path):
        # Check if config.json is missing
        if not os.path.isfile(os.path.join(folder_path, "config.json")):
            video_id = get_video_id_from_folder(folder)
            if video_id:
                remove_summary_link(video_id)

# Close the database connection
conn.close()
