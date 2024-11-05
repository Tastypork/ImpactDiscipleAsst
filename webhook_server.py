#!/usr/bin/env python3
from flask import Flask, request, abort
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from video_utils import log_new_video  # Import log_new_video function

app = Flask(__name__)

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

    # Define the curl command as a list
    command = [
        "curl", "-X", "POST", "https://pubsubhubbub.appspot.com/subscribe",
        "-d", "hub.mode=subscribe",
        "-d", "hub.topic=https://www.youtube.com/xml/feeds/videos.xml?channel_id=UCuKhKyFSA0esUpF09nM9OSA",
        "-d", f"hub.callback={ngrok_url}/webhook",
        "-d", "hub.verify=async"
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

@app.route('/webhook', methods=['GET', 'POST'])
def youtube_webhook():
    # YouTube's verification (subscription confirmation)
    if request.method == 'GET':
        challenge = request.args.get('hub.challenge')
        return challenge, 200

    # YouTube sends data about a new video in POST requests
    elif request.method == 'POST':
        xml_data = request.data  # Get the data YouTube sent as XML
        root = ET.fromstring(xml_data)  # Parse the XML data
        
        # Extract the video ID
        video_id = root.find('.//{http://www.youtube.com/xml/schemas/2015}videoId').text

        # Save the video to your database
        log_new_video(video_id)
        
        return "Success", 200
    else:
        abort(400)


if __name__ == '__main__':
    time.sleep(5)
    # Run the subscription when the app starts
    with app.app_context():
        subscribe_to_youtube()
    app.run(port=5000)
