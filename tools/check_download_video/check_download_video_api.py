import sys, os
import json
import time
import socket
import threading
from flask_cors import CORS
from flask import Flask, request, make_response, jsonify
import traceback
import argparse

app = Flask(__name__)
CORS(app)
data_lock = threading.Lock()

def print_exception():
    try:
        exc_info = sys.exc_info()
    finally:
        traceback.print_exception(*exc_info)
        del exc_info

def save_data():
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(video_data, f, ensure_ascii=False, indent=4)
        f.write('\n')

def load_json_file(path):
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}

def merge_seed(seed_data):
    for video_id, value in seed_data.items():
        if video_id in video_data:
            continue
        if isinstance(value, dict):
            video_data[video_id] = value
        else:
            video_data[video_id] = {
                'status': 'uploaded',
                'source': value,
            }

@app.route('/check_video', methods=['GET'])
def check_video():
    try:
        video_id = request.args.get('video_id')
    except KeyError:
        print_exception()
        return make_response('Invalid request', 400)
    video_exist = video_id in video_data
    
    return jsonify({'exists': video_exist})

@app.route('/reserve_video', methods=['POST', 'GET'])
def reserve_video():
    try:
        payload = request.get_json(silent=True) or {}
        video_id = payload.get('video_id') or request.args.get('video_id')
        metadata = payload.get('metadata') or {}
    except Exception:
        print_exception()
        return make_response('Invalid request', 400)

    if not video_id:
        return make_response('Missing video_id', 400)

    owner = request.args.get('owner') or payload.get('owner') or socket.gethostname()
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    with data_lock:
        existing = video_data.get(video_id)
        if existing:
            return jsonify({'reserved': False, 'exists': True, 'record': existing})

        record = {
            'status': 'reserved',
            'owner': owner,
            'remote_addr': request.remote_addr,
            'reserved_at': now,
            'metadata': metadata,
        }
        video_data[video_id] = record
        save_data()

    return jsonify({'reserved': True, 'exists': False, 'record': record})

@app.route('/add_video', methods=['GET'])
def add_video():
    try:
        video_id = request.args.get('video_id')
    except KeyError:
        print_exception()
        return make_response('Invalid request', 400)
    with data_lock:
        video_exist = video_id in video_data
        if not video_exist:
            video_data[video_id] = {
                'status': 'downloaded',
                'remote_addr': request.remote_addr,
                'downloaded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            }
            save_data()
        
        return jsonify({'message': 'Video added successfully'})

@app.route('/complete_video', methods=['POST', 'GET'])
def complete_video():
    try:
        payload = request.get_json(silent=True) or {}
        video_id = payload.get('video_id') or request.args.get('video_id')
        metadata = payload.get('metadata') or {}
    except Exception:
        print_exception()
        return make_response('Invalid request', 400)

    if not video_id:
        return make_response('Missing video_id', 400)

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with data_lock:
        record = video_data.get(video_id)
        if not isinstance(record, dict):
            record = {'previous_value': record}
        record.update({
            'status': 'downloaded',
            'remote_addr': request.remote_addr,
            'downloaded_at': now,
            'metadata': metadata,
        })
        video_data[video_id] = record
        save_data()

    return jsonify({'message': 'Video completed', 'record': record})

@app.route('/fail_video', methods=['POST', 'GET'])
def fail_video():
    try:
        payload = request.get_json(silent=True) or {}
        video_id = payload.get('video_id') or request.args.get('video_id')
        error = payload.get('error') or request.args.get('error') or ''
    except Exception:
        print_exception()
        return make_response('Invalid request', 400)

    if not video_id:
        return make_response('Missing video_id', 400)

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with data_lock:
        record = video_data.get(video_id)
        if isinstance(record, dict) and record.get('status') == 'reserved':
            del video_data[video_id]
        elif record:
            video_data[video_id] = {
                'status': 'failed',
                'remote_addr': request.remote_addr,
                'failed_at': now,
                'error': error,
                'previous_record': record,
            }
        save_data()

    return jsonify({'message': 'Video failure recorded'})

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
        with data_lock:
            del video_data[video_id]
            save_data()
        
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
    parser.add_argument('--seed', type=str,
                        help='Optional registry JSON to seed duplicate checks without mutating the seed file.',
                        required=False)
    args = parser.parse_args()
    port = args.port
    global video_data
    global data_file
    data_file = args.data
    video_data = load_json_file(data_file)
    seed_data = load_json_file(args.seed)
    if seed_data:
        merge_seed(seed_data)
        save_data()
        
    host = os.environ.get('IP', '0.0.0.0')
    port = int(os.environ.get('PORT', port))
    app.run(host=host, port=port, threaded=False,
            debug=True, use_reloader=False)
