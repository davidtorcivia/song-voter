import os
import secrets
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, jsonify, request, send_file, Response, session, redirect, url_for, flash
import database as db

app = Flask(__name__)

# Data directory for persistent files
DATA_DIR = os.environ.get('DATA_DIR', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Secret key - generate a stable one if not in env
SECRET_KEY_FILE = os.path.join(DATA_DIR, '.secret_key')
if os.environ.get('SECRET_KEY'):
    app.secret_key = os.environ.get('SECRET_KEY')
else:
    try:
        if os.path.exists(SECRET_KEY_FILE):
            with open(SECRET_KEY_FILE, 'r') as f:
                app.secret_key = f.read().strip()
        else:
            app.secret_key = secrets.token_hex(32)
            with open(SECRET_KEY_FILE, 'w') as f:
                f.write(app.secret_key)
    except:
        app.secret_key = secrets.token_hex(32)

# Session config - 2 week lifetime
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=14)

# Configure songs directory from environment or default
SONGS_DIR = os.environ.get('SONGS_DIR', 'songs')

# Uploads directory for assets
UPLOADS_DIR = os.environ.get('UPLOADS_DIR', os.path.join('data', 'uploads'))
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Supported audio extensions
SUPPORTED_EXTENSIONS = ('.wav', '.mp3', '.flac', '.m4a', '.ogg')


# ============ Middleware ============

def admin_required(f):
    """Decorator to require admin authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def check_site_password():
    """Check if site is password protected and user has access."""
    site_password = db.get_setting('site_password', '')
    if site_password and not session.get('site_access') and not session.get('admin'):
        return False
    return True


def run_scan():
    """Scan the songs directory for audio files (internal usage)."""
    if not os.path.exists(SONGS_DIR):
        return 0
    
    count = 0
    for filename in os.listdir(SONGS_DIR):
        if filename.lower().endswith(SUPPORTED_EXTENSIONS):
            full_path = os.path.abspath(os.path.join(SONGS_DIR, filename))
            db.add_song(filename, full_path)
            count += 1
    return count


@app.before_request
def before_request():
    """Check site password before each request."""
    # Skip for static files, admin routes, and gate
    if request.path.startswith('/static') or request.path.startswith('/admin') or request.path == '/gate':
        return
    
    if not check_site_password():
        return redirect(url_for('gate'))


# Add CORS headers for audio (needed for Web Audio API visualizer)
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Range'
    return response


# Inject branding into all templates
@app.context_processor
def inject_branding():
    return {
        'branding': {
            'title': db.get_setting('site_title', 'Song Voter'),
            'description': db.get_setting('site_description', 'Vote on your favorite song versions'),
            'url': db.get_setting('site_url', ''),
            'og_image': db.get_setting('og_image', ''),
            'favicon': db.get_setting('favicon', '/static/favicon.ico'),
        }
    }


# ============ Site Password Gate ============

@app.route('/gate', methods=['GET', 'POST'])
def gate():
    """Site password gate."""
    site_password = db.get_setting('site_password', '')
    
    if not site_password:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == site_password:
            session['site_access'] = True
            return redirect(url_for('index'))
        flash('Incorrect password', 'error')
    
    return render_template('gate.html')


# ============ Public Routes ============

@app.route('/')
def index():
    """Serve the main voting page."""
    branding = {
        'title': db.get_setting('site_title', 'Song Voter'),
        'description': db.get_setting('site_description', 'Vote on your favorite song versions'),
        'url': db.get_setting('site_url', ''),
        'og_image': db.get_setting('og_image', ''),
        'favicon': db.get_setting('favicon', '/static/favicon.ico'),
    }
    }
    
    # Server-side caching: Get songs from DB
    songs = db.get_all_songs()
    
    # If DB is empty, run a scan automatically so first load isn't empty
    if not songs:
        run_scan()
        songs = db.get_all_songs()
        
    base_names = db.get_unique_base_names()
    
    return render_template('index.html', branding=branding, songs=songs, base_names=base_names)


@app.route('/results')
def results():
    """Serve the results page based on visibility setting."""
    visibility = db.get_setting('results_visibility', 'public')
    
    # Admin always has access
    if session.get('admin'):
        return render_template('results.html')
    
    if visibility == 'hidden':
        flash('Results are not publicly available', 'error')
        return redirect(url_for('index'))
    
    if visibility == 'until_voting_ends':
        from datetime import datetime
        voting_end = db.get_setting('voting_end', '')
        if voting_end:
            try:
                end_dt = datetime.fromisoformat(voting_end)
                if datetime.now() < end_dt:
                    flash('Results will be available after voting ends', 'error')
                    return redirect(url_for('index'))
            except ValueError:
                pass
    
    return render_template('results.html')


@app.route('/help')
def help_page():
    """Serve the help page."""
    return render_template('help.html')


@app.route('/play/<int:song_id>')
def play_song(song_id):
    """Single song player (no voting)."""
    song = db.get_song_by_id(song_id)
    if not song:
        flash('Song not found', 'error')
        return redirect(url_for('index'))
    return render_template('play.html', song=song)


@app.route('/vote/<base_name>')
def vote_track(base_name):
    """Direct link to vote on a specific track (all versions)."""
    songs = db.get_songs_by_base_name(base_name)
    if not songs:
        flash('Track not found', 'error')
        return redirect(url_for('index'))
    return render_template('index.html', direct_track=base_name)


# ============ API Routes ============

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
    """Stream audio file for a song (loudness normalized)."""
    song = db.get_song_by_id(song_id)
    if not song:
        return jsonify({'error': 'Song not found'}), 404
    
    full_path = song['full_path']
    if not os.path.exists(full_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    # Use normalized version if available
    try:
        import audio_normalize
        full_path = audio_normalize.get_or_normalize(full_path)
    except Exception as e:
        print(f"Normalization error: {e}")
        # Fall back to original
    
    # Detect MIME type based on file extension
    ext = os.path.splitext(full_path)[1].lower()
    mime_types = {
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.flac': 'audio/flac',
        '.m4a': 'audio/mp4',
        '.ogg': 'audio/ogg',
    }
    mime_type = mime_types.get(ext, 'audio/mpeg')
    
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
            mimetype=mime_type,
            direct_passthrough=True
        )
        response.headers['Content-Range'] = f'bytes {byte_start}-{byte_end}/{file_size}'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = length
        return response
    
    return send_file(full_path, mimetype=mime_type)


@app.route('/api/songs/<int:song_id>/vote', methods=['POST'])
def vote(song_id):
    """Submit a vote for a song."""
    song = db.get_song_by_id(song_id)
    if not song:
        return jsonify({'error': 'Song not found'}), 404
    
    # Check voting time window (admin bypass)
    if not session.get('admin'):
        from datetime import datetime
        now = datetime.now()
        
        voting_start = db.get_setting('voting_start', '')
        voting_end = db.get_setting('voting_end', '')
        
        if voting_start:
            try:
                start_dt = datetime.fromisoformat(voting_start)
                if now < start_dt:
                    return jsonify({'error': 'Voting has not started yet'}), 403
            except ValueError:
                pass
        
        if voting_end:
            try:
                end_dt = datetime.fromisoformat(voting_end)
                if now > end_dt:
                    return jsonify({'error': 'Voting has ended'}), 403
            except ValueError:
                pass
    
    data = request.get_json()
    thumbs_up = data.get('thumbs_up')
    rating = data.get('rating')
    
    if thumbs_up is None and rating is None:
        return jsonify({'error': 'Must provide thumbs_up or rating'}), 400
    
    if rating is not None and (rating < 1 or rating > 10):
        return jsonify({'error': 'Rating must be between 1 and 10'}), 400
    
    # Check voting restrictions (admin bypass)
    voter_id = None
    if not session.get('admin'):
        voter_id = db.get_voter_id(request)
        if voter_id and db.has_voted(song_id, voter_id):
            return jsonify({'error': 'You have already voted on this song'}), 403
    
    db.add_vote(song_id, thumbs_up, rating, voter_id)
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
    visibility = db.get_setting('results_visibility', 'public')
    
    # Admin bypass
    if not session.get('admin'):
        if visibility == 'hidden':
            return jsonify({'error': 'Results are not publicly available'}), 403
        
        if visibility == 'until_voting_ends':
            from datetime import datetime
            voting_end = db.get_setting('voting_end', '')
            if voting_end:
                try:
                    end_dt = datetime.fromisoformat(voting_end)
                    if datetime.now() < end_dt:
                        return jsonify({'error': 'Results available after voting ends'}), 403
                except ValueError:
                    pass
    
    results = db.get_all_results()
    return jsonify({'results': results})


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get frontend configuration settings."""
    return jsonify({
        'min_listen_time': int(db.get_setting('min_listen_time', '20')),
        'disable_skip': db.get_setting('disable_skip', 'false') == 'true',
        'site_title': db.get_setting('site_title', 'Song Voter'),
        'voting_start': db.get_setting('voting_start', ''),
        'voting_end': db.get_setting('voting_end', ''),
    })


@app.route('/api/scan', methods=['POST'])
def scan_folder():
    """Scan the songs directory for audio files."""
    if not os.path.exists(SONGS_DIR):
        return jsonify({'error': f'Songs directory not found: {SONGS_DIR}'}), 400
    
    count = run_scan()
    
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


# ============ Admin Routes ============

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page."""
    # If no admins exist, redirect to setup
    if db.admin_count() == 0:
        return redirect(url_for('admin_setup'))
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        admin = db.verify_admin(username, password)
        if admin:
            session.permanent = True  # Use 2-week session lifetime
            session['admin'] = admin
            session['site_access'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'error')
    
    return render_template('admin/login.html')


@app.route('/admin/setup', methods=['GET', 'POST'])
def admin_setup():
    """First-time admin setup."""
    if db.admin_count() > 0:
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        if username and password:
            db.create_admin(username, password)
            flash('Admin account created! Please login.', 'success')
            return redirect(url_for('admin_login'))
        flash('Username and password required', 'error')
    
    return render_template('admin/setup.html')


@app.route('/admin/logout')
def admin_logout():
    """Admin logout."""
    session.pop('admin', None)
    return redirect(url_for('index'))


@app.route('/admin/')
@admin_required
def admin_dashboard():
    """Admin dashboard."""
    settings = db.get_all_settings()
    songs = db.get_all_songs()
    admins = db.get_all_admins()
    return render_template('admin/dashboard.html', 
                         settings=settings, 
                         songs=songs, 
                         admins=admins)


@app.route('/admin/settings', methods=['POST'])
@admin_required
def admin_update_settings():
    """Update settings."""
    data = request.get_json()
    
    allowed_keys = [
        'site_password', 'voting_restriction', 'results_visibility',
        'voting_start', 'voting_end', 'min_listen_time', 'disable_skip',
        'site_title', 'site_description', 'site_url', 'og_image', 'favicon'
    ]
    
    for key, value in data.items():
        if key in allowed_keys:
            db.set_setting(key, value)
    
    return jsonify({'success': True})


@app.route('/admin/upload-asset', methods=['POST'])
@admin_required
def admin_upload_asset():
    """Upload an asset (favicon, OG image)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    asset_type = request.form.get('type', '')  # 'favicon' or 'og_image'
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if asset_type not in ['favicon', 'og_image']:
        return jsonify({'error': 'Invalid asset type'}), 400
    
    # Validate file type
    allowed_ext = {'.png', '.jpg', '.jpeg', '.ico', '.gif', '.webp'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({'error': f'Invalid file type. Use: {", ".join(allowed_ext)}'}), 400
    
    # Save file with asset type as name
    filename = f'{asset_type}{ext}'
    filepath = os.path.join(UPLOADS_DIR, filename)
    file.save(filepath)
    
    # Update setting with path
    asset_url = f'/uploads/{filename}'
    db.set_setting(asset_type, asset_url)
    
    return jsonify({'success': True, 'url': asset_url})


@app.route('/admin/delete-asset/<asset_type>', methods=['DELETE'])
@admin_required
def admin_delete_asset(asset_type):
    """Delete an uploaded asset."""
    if asset_type not in ['favicon', 'og_image']:
        return jsonify({'error': 'Invalid asset type'}), 400
    
    # Get current value
    current = db.get_setting(asset_type, '')
    if current.startswith('/uploads/'):
        filepath = os.path.join(UPLOADS_DIR, os.path.basename(current))
        if os.path.exists(filepath):
            os.remove(filepath)
    
    db.set_setting(asset_type, '')
    return jsonify({'success': True})


@app.route('/uploads/<filename>')
def serve_upload(filename):
    """Serve uploaded files."""
    return send_file(os.path.join(UPLOADS_DIR, filename))


@app.route('/admin/upload', methods=['POST'])
@admin_required
def admin_upload_song():
    """Upload a new song file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check extension
    filename = file.filename
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        return jsonify({'error': f'Unsupported format. Use: {", ".join(SUPPORTED_EXTENSIONS)}'}), 400
    
    # Ensure songs directory exists
    os.makedirs(SONGS_DIR, exist_ok=True)
    
    # Save file
    full_path = os.path.abspath(os.path.join(SONGS_DIR, filename))
    
    # Check if already exists
    if os.path.exists(full_path):
        return jsonify({'error': 'File already exists'}), 400
    
    file.save(full_path)
    
    # Add to database
    song_id = db.add_song(filename, full_path)
    
    # Trigger normalization in background (optional - could be slow)
    try:
        import audio_normalize
        audio_normalize.get_or_normalize(full_path)
    except Exception as e:
        print(f"Normalization error: {e}")
    
    return jsonify({
        'success': True,
        'song_id': song_id,
        'filename': filename
    })


@app.route('/admin/songs/<int:song_id>', methods=['DELETE'])
@admin_required
def admin_delete_song(song_id):
    """Delete a song."""
    full_path = db.delete_song(song_id)
    
    if full_path:
        # Try to delete normalized version
        try:
            import audio_normalize
            normalized_path = audio_normalize.get_normalized_path(full_path)
            if os.path.exists(normalized_path):
                os.remove(normalized_path)
        except Exception as e:
            print(f"Error deleting normalized file: {e}")
        
        return jsonify({'success': True})
    
    return jsonify({'error': 'Song not found'}), 404


@app.route('/admin/admins', methods=['POST'])
@admin_required
def admin_create_admin():
    """Create a new admin."""
    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    admin_id = db.create_admin(username, password)
    if admin_id:
        return jsonify({'success': True, 'id': admin_id})
    return jsonify({'error': 'Username already exists'}), 400


@app.route('/admin/admins/<int:admin_id>', methods=['DELETE'])
@admin_required
def admin_delete_admin(admin_id):
    """Delete an admin."""
    # Prevent deleting yourself
    if session.get('admin', {}).get('id') == admin_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    # Ensure at least one admin remains
    if db.admin_count() <= 1:
        return jsonify({'error': 'Cannot delete the last admin'}), 400
    
    # Protect first admin (owner)
    first_admin = db.get_first_admin()
    if first_admin and first_admin['id'] == admin_id:
        return jsonify({'error': 'Cannot delete the owner admin'}), 400
    
    if db.delete_admin(admin_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Admin not found'}), 404


# Initialize database on module import (works with gunicorn)
db.init_db()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
