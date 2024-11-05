import os
import json
import sqlite3

# Set paths
parent_folder = '../html/sermons'
db_path = 'video_data.db'
table_name = 'video_tags'

# Connect to SQLite database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Iterate through folders in the parent folder
for folder_name in os.listdir(parent_folder):
    folder_path = os.path.join(parent_folder, folder_name)

    # Ensure it's a directory
    if os.path.isdir(folder_path):
        try:
            # Extract video_id from folder name
            video_id = '_'.join(folder_name.split('_')[1:])

            # Path to config.json within the folder
            config_path = os.path.join(folder_path, 'config.json')

            # Process if config.json exists
            if os.path.exists(config_path):
                with open(config_path, 'r') as config_file:
                    config_data = json.load(config_file)

                # Extract tags from config.json
                tags = config_data['tags']

                # Insert each tag into the database
                for tag in tags:
                    print(f'{video_id}, {tag}')
                    cursor.execute(f"""
                    INSERT INTO {table_name} (video_id, tag)
                    VALUES (?, ?)
                    """, (video_id, tag))

                conn.commit()

        except (IndexError, json.JSONDecodeError, KeyError) as e:
            print(f"Skipping folder {folder_name} due to an error: {e}")

# Close the database connection
conn.close()
print("Processing completed.")