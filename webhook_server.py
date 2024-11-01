from flask import Flask, request, abort
import xml.etree.ElementTree as ET
from video_utils import log_new_video  # Import log_new_video function

app = Flask(__name__)

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
    app.run(port=5000)
