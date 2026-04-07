#!/usr/bin/env python3
from flask import Flask, request, abort
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from video_utils import ingest_video, IngestResult, load_app_config
from video_sync import fetch_all_channel_playlist_video_ids

app = Flask(__name__)
PLAYLIST_MEMBERSHIP_CHECK_ATTEMPTS = 3
PLAYLIST_MEMBERSHIP_RETRY_SECONDS = 5


def git_push(commit_message: str = "Auto-commit generated data") -> None:
    """
    Stage and publish regenerated sermon artifacts.
    Uses the current process identity and surfaces command errors in logs.
    """
    paths_to_stage = ["html/sermons", "html/latest_sermons.json"]
    try:
        subprocess.run(["git", "add"] + paths_to_stage, check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Changes committed and pushed successfully.")
    except subprocess.CalledProcessError as e:
        print("An error occurred while pushing generated artifacts:", e)

# Function to subscribe to YouTube Pub/Sub using the curl command
def subscribe_to_youtube():
    # Fetch NGROK_URL from environment variable
    curl_command = "curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[] | select(.config.addr == \"http://localhost:5000\") | .public_url'"

    # Run the curl command and capture the output
    result = subprocess.run(curl_command, shell=True, capture_output=True, text=True)

    # Check if the curl command was successful
    if result.returncode == 0:
        public_url = result.stdout.strip()  # Capture the output and remove any trailing newline
        if public_url:
            # Set the environment variable
            os.environ["NGROK_URL"] = public_url
            print("NGROK_URL set to:", public_url)
    else:
        print("No matching tunnel found.")
    ngrok_url = os.getenv("NGROK_URL")
    if not ngrok_url:
        print("Error: NGROK_URL environment variable is not set.")
        return

    channel_id = load_app_config()["channel_id"]
    topic = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    command = [
        "curl", "-X", "POST", "https://pubsubhubbub.appspot.com/subscribe",
        "-d", "hub.mode=subscribe",
        "-d", f"hub.topic={topic}",
        "-d", f"hub.callback={ngrok_url}/webhook",
        "-d", "hub.verify=async",
    ]

    # Run the curl command
    result = subprocess.run(command, capture_output=True, text=True)

    # Check the result
    if result.returncode == 0:
        print("Successfully sent subscription request to YouTube Pub/Sub.")
        print("Response:", result.stdout)
    else:
        print("Failed to send subscription request.")
        print("Error:", result.stderr)


def _video_is_in_any_channel_playlist(video_id: str) -> bool:
    """
    Pub/Sub notifies for channel uploads feed, which can include live streams.
    Enforce playlist policy here so webhook behavior matches sync behavior.
    Retry briefly because playlist assignment can lag upload notification.
    """
    cfg = load_app_config()
    channel_id = cfg["channel_id"]
    api_key = cfg["yt_token"]
    for attempt in range(1, PLAYLIST_MEMBERSHIP_CHECK_ATTEMPTS + 1):
        try:
            playlist_ids = fetch_all_channel_playlist_video_ids(channel_id, api_key)
        except Exception as e:
            print(f"Playlist membership check failed for {video_id}: {e}")
            return False
        if video_id in set(playlist_ids):
            return True
        if attempt < PLAYLIST_MEMBERSHIP_CHECK_ATTEMPTS:
            time.sleep(PLAYLIST_MEMBERSHIP_RETRY_SECONDS)
    return False


@app.route('/webhook', methods=['GET', 'POST'])
def youtube_webhook():
    # YouTube's verification (subscription confirmation)
    if request.method == 'GET':
        challenge = request.args.get('hub.challenge')
        return challenge, 200

    # YouTube sends data about a new video in POST requests
    elif request.method == 'POST':
        xml_data = request.data  # Get the data YouTube sent as XML
        try:
            root = ET.fromstring(xml_data)  # Parse the XML data
        except ET.ParseError:
            return "Ignored: malformed XML", 200
        
        # Extract the video ID
        video_node = root.find('.//{http://www.youtube.com/xml/schemas/2015}videoId')
        if video_node is None or not video_node.text:
            return "Ignored: no videoId in notification", 200
        video_id = video_node.text

        if not _video_is_in_any_channel_playlist(video_id):
            print(f"Ignoring {video_id}: not found in any channel playlist.")
            return "Ignored: not in channel playlists", 200

        result = ingest_video(video_id)
        if result == IngestResult.FAILED:
            return "Failed, see log", 400
        if result == IngestResult.SUCCESS:
            git_push()
        return "Success", 200
    else:
        abort(400)


if __name__ == '__main__':
    time.sleep(5)
    # Run the subscription when the app starts
    with app.app_context():
        subscribe_to_youtube()
    app.run(port=5000)
