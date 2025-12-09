import os
import mimetypes
from flask import Flask, render_template, jsonify, request, send_file, Response
import database as db

app = Flask(__name__)

# Configure songs directory from environment or default
SONGS_DIR = os.environ.get('SONGS_DIR', 'songs')


@app.route('/')
def index():
    """Serve the main voting page."""
    return render_template('index.html')


@app.route('/results')
def results():
    """Serve the results page."""
    return render_template('results.html')


@app.route('/api/songs', methods=['GET'])
def get_songs():
    """Get all songs, optionally filtered by base_name."""
    base_name = request.args.get('base_name')
    
    if base_name:
        songs = db.get_songs_by_base_name(base_name)
    else:
        songs = db.get_all_songs()
    
    return jsonify({'songs': songs})


@app.route('/api/songs/<int:song_id>/audio', methods=['GET'])
def get_audio(song_id):
    """Stream audio file for a song."""
    song = db.get_song_by_id(song_id)
    if not song:
        return jsonify({'error': 'Song not found'}), 404
    
    full_path = song['full_path']
    if not os.path.exists(full_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    # Get file size for range requests
    file_size = os.path.getsize(full_path)
    
    # Handle range requests for audio scrubbing
    range_header = request.headers.get('Range')
    if range_header:
        byte_start = 0
        byte_end = file_size - 1
        
        range_match = range_header.replace('bytes=', '').split('-')
        if range_match[0]:
            byte_start = int(range_match[0])
        if range_match[1]:
            byte_end = int(range_match[1])
        
        length = byte_end - byte_start + 1
        
        def generate():
            with open(full_path, 'rb') as f:
                f.seek(byte_start)
                remaining = length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        
        response = Response(
            generate(),
            status=206,
            mimetype='audio/wav',
            direct_passthrough=True
        )
        response.headers['Content-Range'] = f'bytes {byte_start}-{byte_end}/{file_size}'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = length
        return response
    
    return send_file(full_path, mimetype='audio/wav')


@app.route('/api/songs/<int:song_id>/vote', methods=['POST'])
def vote(song_id):
    """Submit a vote for a song."""
    song = db.get_song_by_id(song_id)
    if not song:
        return jsonify({'error': 'Song not found'}), 404
    
    data = request.get_json()
    thumbs_up = data.get('thumbs_up')  # True, False, or None
    rating = data.get('rating')  # 1-10 or None
    
    if thumbs_up is None and rating is None:
        return jsonify({'error': 'Must provide thumbs_up or rating'}), 400
    
    if rating is not None and (rating < 1 or rating > 10):
        return jsonify({'error': 'Rating must be between 1 and 10'}), 400
    
    db.add_vote(song_id, thumbs_up, rating)
    stats = db.get_song_stats(song_id)
    
    return jsonify({'success': True, 'stats': stats})


@app.route('/api/base-names', methods=['GET'])
def get_base_names():
    """Get all unique base names for the song selector."""
    names = db.get_unique_base_names()
    return jsonify({'base_names': names})


@app.route('/api/results', methods=['GET'])
def get_results():
    """Get aggregate results for all songs."""
    results = db.get_all_results()
    return jsonify({'results': results})


@app.route('/api/scan', methods=['POST'])
def scan_folder():
    """Scan the songs directory for WAV files."""
    if not os.path.exists(SONGS_DIR):
        return jsonify({'error': f'Songs directory not found: {SONGS_DIR}'}), 400
    
    count = 0
    for filename in os.listdir(SONGS_DIR):
        if filename.lower().endswith('.wav'):
            full_path = os.path.abspath(os.path.join(SONGS_DIR, filename))
            db.add_song(filename, full_path)
            count += 1
    
    songs = db.get_all_songs()
    base_names = db.get_unique_base_names()
    
    return jsonify({
        'success': True,
        'count': count,
        'songs': songs,
        'base_names': base_names
    })


@app.route('/api/clear', methods=['POST'])
def clear_data():
    """Clear all data and rescan."""
    db.clear_all_data()
    return jsonify({'success': True})


# ============ HEOS Endpoints ============

@app.route('/api/heos/discover', methods=['POST'])
def heos_discover():
    """Discover HEOS devices on the network."""
    import heos
    devices = heos.discover_heos_devices(timeout=3)
    return jsonify({'devices': devices})


@app.route('/api/heos/devices', methods=['GET'])
def heos_devices():
    """Get cached HEOS devices."""
    import heos
    devices = heos.get_cached_devices()
    return jsonify({'devices': devices})


@app.route('/api/heos/play', methods=['POST'])
def heos_play():
    """Tell a HEOS device to play a song."""
    import heos
    data = request.get_json()
    
    host = data.get('host')
    pid = data.get('pid')
    song_id = data.get('song_id')
    
    if not all([host, pid, song_id]):
        return jsonify({'error': 'Missing host, pid, or song_id'}), 400
    
    # Build the full audio URL
    # Use the request's host to build the URL the HEOS device can reach
    audio_url = f"{request.url_root}api/songs/{song_id}/audio"
    
    success = heos.play_url(host, pid, audio_url)
    
    if success:
        return jsonify({'success': True, 'url': audio_url})
    else:
        return jsonify({'error': 'Failed to play on HEOS device'}), 500


@app.route('/api/heos/stop', methods=['POST'])
def heos_stop():
    """Stop playback on a HEOS device."""
    import heos
    data = request.get_json()
    
    host = data.get('host')
    pid = data.get('pid')
    
    if not all([host, pid]):
        return jsonify({'error': 'Missing host or pid'}), 400
    
    success = heos.stop_playback(host, pid)
    return jsonify({'success': success})


# ============ AirPlay Endpoints ============

@app.route('/api/airplay/discover', methods=['POST'])
def airplay_discover():
    """Discover AirPlay devices on the network."""
    import airplay
    if not airplay.is_available():
        return jsonify({'error': 'pyatv not installed', 'devices': []}), 200
    
    devices = airplay.discover_airplay_devices(timeout=5)
    return jsonify({'devices': devices})


@app.route('/api/airplay/devices', methods=['GET'])
def airplay_devices():
    """Get cached AirPlay devices."""
    import airplay
    if not airplay.is_available():
        return jsonify({'devices': []})
    
    devices = airplay.get_cached_devices()
    return jsonify({'devices': devices})


@app.route('/api/airplay/play', methods=['POST'])
def airplay_play():
    """Stream a song to an AirPlay device."""
    import airplay
    if not airplay.is_available():
        return jsonify({'error': 'pyatv not installed'}), 500
    
    data = request.get_json()
    address = data.get('address')
    song_id = data.get('song_id')
    
    if not all([address, song_id]):
        return jsonify({'error': 'Missing address or song_id'}), 400
    
    # Build the full audio URL
    audio_url = f"{request.url_root}api/songs/{song_id}/audio"
    
    success = airplay.stream_url(address, audio_url)
    
    if success:
        return jsonify({'success': True, 'url': audio_url})
    else:
        return jsonify({'error': 'Failed to stream to AirPlay device'}), 500


@app.route('/api/airplay/stop', methods=['POST'])
def airplay_stop():
    """Stop playback on an AirPlay device."""
    import airplay
    if not airplay.is_available():
        return jsonify({'error': 'pyatv not installed'}), 500
    
    data = request.get_json()
    address = data.get('address')
    
    if not address:
        return jsonify({'error': 'Missing address'}), 400
    
    success = airplay.stop_playback(address)
    return jsonify({'success': success})


if __name__ == '__main__':
    db.init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
