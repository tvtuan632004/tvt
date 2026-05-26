import sys, os
import json
import requests
from flask_cors import CORS
from flask import Flask, request, make_response, jsonify
import traceback
import argparse

app = Flask(__name__)
CORS(app)

def print_exception():
    try:
        exc_info = sys.exc_info()
    finally:
        traceback.print_exception(*exc_info)
        del exc_info

@app.route('/check_video', methods=['GET'])
def check_video():
    try:
        video_id = request.args.get('video_id')
    except KeyError:
        print_exception()
        return make_response('Invalid request', 400)
    video_exist = False
    if video_id in video_data:
        video_exist = True
    
    return jsonify({'exists': video_exist})

@app.route('/add_video', methods=['GET'])
def add_video():
    try:
        video_id = request.args.get('video_id')
    except KeyError:
        print_exception()
        return make_response('Invalid request', 400)
    video_exist = False
    if video_id in video_data:
        video_exist = True
    
    if not video_exist:
        video_data[video_id] = request.remote_addr
        with open(data_file, 'w') as f:
            json.dump(video_data, f, ensure_ascii=False, indent=4)
        
        return jsonify({'message': 'Video added successfully'})
    else:
        return jsonify({'message': 'Video already exists'})

@app.route('/remove_video', methods=['GET'])
def remove_video():
    try:
        video_id = request.args.get('video_id')
    except KeyError:
        print_exception()
        return make_response('Invalid request', 400)
    video_exist = False
    if video_id in video_data:
        video_exist = True
    
    if video_exist:
        del video_data[video_id]
        with open(data_file, 'w') as f:
            json.dump(video_data, f, ensure_ascii=False, indent=4)
        
        return jsonify({'message': 'Video removed successfully'})
    else:
        return jsonify({'message': 'Video is not exists'})

@app.route('/list_downloaded_videos', methods=['GET'])
def list_downloaded_videos():
    return jsonify(video_data)

@app.route('/get_info', methods=['GET'])
def get_info():
    try:
        video_id = request.args.get('video_id')
    except KeyError:
        print_exception()
        return make_response('Invalid request', 400)
    if video_id not in video_data:
        return make_response('Video not Exist', 404)
    else:
        return jsonify({video_id: video_data[video_id]})

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--data', type=str,
                        help='Stored data file', default='video_data.json', required=False)
    parser.add_argument('-p', '--port', type=int, default=8020,
                        help='Service port', required=False)
    args = parser.parse_args()
    port = args.port
    global video_data
    global data_file
    data_file = args.data
    if os.path.isfile(data_file):
        with open(data_file) as f:
            video_data = json.load(f)
    else:
        video_data = {}
        
    host = os.environ.get('IP', '0.0.0.0')
    port = int(os.environ.get('PORT', port))
    app.run(host=host, port=port, threaded=False,
            debug=True, use_reloader=False)