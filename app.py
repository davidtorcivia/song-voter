import os
import secrets
import time
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, jsonify, request, send_file, Response, session, redirect, url_for, flash
from flask_wtf.csrf import CSRFProtect
import database as db
import waveform
import audio_normalize


# ============ Rate Limiter ============

class VoteRateLimiter:
    """In-memory rate limiter with sliding window and size cap."""
    
    def __init__(self, max_votes=30, window_secs=300, max_ips=10000):
        self.votes = {}  # {ip: [timestamp, timestamp, ...]}
        self.max_votes = max_votes
        self.window_secs = window_secs
        self.max_ips = max_ips
    
    def _evict_oldest(self, count):
        """Evict oldest entries when dict gets too large."""
        if not self.votes:
            return
        # Sort IPs by their oldest timestamp
        sorted_ips = sorted(self.votes.keys(), key=lambda ip: min(self.votes[ip]) if self.votes[ip] else 0)
        for ip in sorted_ips[:count]:
            del self.votes[ip]
    
    def check(self, ip):
        """Check if IP can vote. Returns (allowed, retry_after_secs)."""
        now = time.time()
        
        # Evict old entries if dict too large
        if len(self.votes) > self.max_ips:
            self._evict_oldest(int(self.max_ips * 0.25))
        
        # Clean old timestamps for this IP
        if ip in self.votes:
            self.votes[ip] = [t for t in self.votes[ip] if now - t < self.window_secs]
            if not self.votes[ip]:
                del self.votes[ip]
        
        # Check limit
        if ip in self.votes and len(self.votes[ip]) >= self.max_votes:
            retry_after = self.window_secs - (now - self.votes[ip][0])
            return False, max(1, int(retry_after))
        
        # Record vote
        self.votes.setdefault(ip, []).append(now)
        return True, 0

# Global rate limiter instance
vote_limiter = VoteRateLimiter(max_votes=30, window_secs=300, max_ips=10000)

app = Flask(__name__)
csrf = CSRFProtect(app)

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
# Secure cookies
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# Configure songs directory from environment or default
SONGS_DIR = os.environ.get('SONGS_DIR', 'songs')

# Uploads directory for assets
UPLOADS_DIR = os.environ.get('UPLOADS_DIR', os.path.join('data', 'uploads'))
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Supported audio extensions
SUPPORTED_EXTENSIONS = ('.wav', '.mp3', '.flac', '.m4a', '.ogg')


# ============ Middleware ============

def admin_required(f):
    """Decorator to require any authenticated admin/editor/owner."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_or_owner_required(f):
    """Decorator to require admin or owner role (excludes editors)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin = session.get('admin')
        if not admin:
            return redirect(url_for('admin_login'))
        if admin.get('role') not in ('admin', 'owner'):
            flash('You do not have permission to access this page', 'error')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def owner_required(f):
    """Decorator to require owner role only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin = session.get('admin')
        if not admin:
            return redirect(url_for('admin_login'))
        if admin.get('role') != 'owner':
            flash('Only owners can access this feature', 'error')
            return redirect(url_for('admin_dashboard'))
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
            song_id = db.add_song(filename, full_path)
            if song_id:
                # Generate waveform in background (lightweight)
                try:
                    waveform.get_or_generate_waveform(full_path, song_id)
                except Exception as e:
                    print(f"Waveform generation error: {e}")
            count += 1
    return count


@app.before_request
def before_request():
    """Check site password before each request."""
    # Skip for static files, admin routes, gate, and vote blocks
    if (request.path.startswith('/static') or 
        request.path.startswith('/admin') or 
        request.path.startswith('/vote/') or
        request.path == '/gate'):
        return
    
    if not check_site_password():
        return redirect(url_for('gate'))


# Add CORS and security headers
@app.after_request
def add_headers(response):
    # CORS headers for audio (needed for Web Audio API visualizer)
    # Restrict to audio/static endpoints if possible, but for now keep * for compatibility
    if request.path.startswith('/api/songs/') and 'audio' in request.path:
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Range'
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Content Security Policy (Example - adjust based on needs)
    # Allowing unsafe-inline because of extensive use in templates/Alpine.js
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob: data:; "
        "connect-src 'self'; "
        "object-src 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    
    # HSTS (1 year)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
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
            'accent_color': db.get_setting('accent_color', '#ffffff'),
            'visualizer_mode': db.get_setting('visualizer_mode', 'bars'),
            'visualizer_color': db.get_setting('visualizer_color', ''),
            'tracking_code': db.get_setting('tracking_code', ''),
            'cast_enabled': db.get_setting('cast_enabled', 'false'),
            'cast_app_id': db.get_setting('cast_app_id', ''),
            'cast_receiver_type': db.get_setting('cast_receiver_type', 'default'),
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
    """Serve the main voting page (or closed page if homepage is closed)."""
    # Check if homepage is closed
    if db.get_setting('homepage_closed', 'false') == 'true':
        return render_template('closed.html')
    
    branding = {
        'title': db.get_setting('site_title', 'Song Voter'),
        'description': db.get_setting('site_description', 'Vote on your favorite song versions'),
        'url': db.get_setting('site_url', ''),
        'og_image': db.get_setting('og_image', ''),
        'favicon': db.get_setting('favicon', '/static/favicon.ico'),
        'accent_color': db.get_setting('accent_color', '#ffffff'),
        'visualizer_mode': db.get_setting('visualizer_mode', 'bars'),
        'visualizer_color': db.get_setting('visualizer_color', ''),
        'cast_enabled': db.get_setting('cast_enabled', 'false'),
        'cast_app_id': db.get_setting('cast_app_id', ''),
        'cast_receiver_type': db.get_setting('cast_receiver_type', 'default'),
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


@app.route('/play/<slug>')
def play_song(slug):
    """Single song player (no voting)."""
    song = db.get_song_by_slug(slug)
    if not song:
        return render_template('not_found.html', message='Song not found'), 404
    return render_template('play.html', song=song)


@app.route('/cast-receiver')
def cast_receiver():
    """Serve the Custom Cast Receiver."""
    return render_template('cast_receiver.html')


@app.route('/vote/<base_name>')
def vote_track(base_name):
    """Direct link to vote on a specific track (all versions)."""
    songs = db.get_songs_by_base_name(base_name)
    if not songs:
        flash('Track not found', 'error')
        return redirect(url_for('index'))
    return render_template('index.html', direct_track=base_name)


# ============ Vote Block Routes ============

@app.route('/vote/block/<slug>')
def vote_block(slug):
    """Vote block entry point."""
    block = db.get_vote_block_by_slug(slug)
    if not block:
        flash('Vote block not found', 'error')
        return redirect(url_for('index'))
    
    # Check if expired
    if db.is_block_expired(block):
        return render_template('block_expired.html', block=block)
    
    # Check if password protected
    if block.get('password_hash') and not session.get(f'block_access_{block["id"]}'):
        return redirect(url_for('vote_block_auth', slug=slug))
    
    # Get block songs
    songs = db.get_vote_block_songs(block['id'])
    if not songs:
        flash('This vote block has no songs', 'error')
        return redirect(url_for('index'))
    
    settings = db.get_all_settings()
    return render_template('block.html', block=block, songs=songs, settings=settings)


@app.route('/vote/block/<slug>/auth', methods=['GET', 'POST'])
def vote_block_auth(slug):
    """Password gate for protected blocks."""
    block = db.get_vote_block_by_slug(slug)
    if not block:
        flash('Vote block not found', 'error')
        return redirect(url_for('index'))
    
    # If no password required, redirect to block
    if not block.get('password_hash'):
        return redirect(url_for('vote_block', slug=slug))
    
    # Check if expired
    if db.is_block_expired(block):
        return render_template('block_expired.html', block=block)
    
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if db.verify_block_password(block, password):
            session[f'block_access_{block["id"]}'] = True
            return redirect(url_for('vote_block', slug=slug))
        error = 'Incorrect password'
    
    return render_template('block_auth.html', block=block, error=error)

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
    
    # Path Traversal Protection
    # Verify file is within permitted directories
    abs_file = os.path.abspath(full_path)
    abs_songs = os.path.abspath(SONGS_DIR)
    abs_norm = os.path.abspath(audio_normalize.NORMALIZED_DIR)
    
    if not (abs_file.startswith(abs_songs) or abs_file.startswith(abs_norm)):
        app.logger.error(f"Path traversal attempt blocked: {full_path}")
        return jsonify({'error': 'Access denied'}), 403
        
    if not os.path.exists(full_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    # Use normalized version if available
    try:
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
    try:
        """Submit a vote for a song."""
        # Rate limiting (admin bypass)
        if not session.get('admin'):
            client_ip = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr
            allowed, retry_after = vote_limiter.check(client_ip)
            if not allowed:
                response = jsonify({'error': 'Too many votes. Please slow down.', 'retry_after': retry_after})
                response.headers['Retry-After'] = str(retry_after)
                return response, 429
        
        song = db.get_song_by_id(song_id)
        if not song:
            return jsonify({'error': 'Song not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        thumbs_up = data.get('thumbs_up')
        rating = data.get('rating')
        block_id = data.get('block_id')
        
        if thumbs_up is None and rating is None:
            return jsonify({'error': 'Must provide thumbs_up or rating'}), 400
        
        if rating is not None and (rating < 1 or rating > 10):
            return jsonify({'error': 'Rating must be between 1 and 10'}), 400
        
        # Handle block-specific voting
        block = None
        if block_id:
            block = db.get_vote_block_by_id(block_id)
            if not block:
                return jsonify({'error': 'Vote block not found'}), 404
            
            # Check if block is expired
            if db.is_block_expired(block):
                return jsonify({'error': 'This vote block has expired'}), 403
        
        # Check voting time window (admin bypass, skip for block voting)
        if not session.get('admin') and not block_id:
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
        
        # Check voting restrictions (admin bypass)
        voter_id = None
        if not session.get('admin'):
            # Determine which voting restriction to use
            # Block-specific restriction takes precedence if set
            voting_restriction = 'none'
            if block and block.get('voting_restriction'):
                voting_restriction = block['voting_restriction']
            else:
                voting_restriction = db.get_setting('voting_restriction', 'none')
            
            # Only get voter_id if restriction is set
            if voting_restriction != 'none':
                voter_id = db.get_voter_id(request)
            
            # Check one-time-use block restriction (voter can only vote once per block)
            if block and block.get('one_time_use') and voter_id:
                if db.has_voted_in_block(voter_id, block_id):
                    return jsonify({'error': 'You have already voted in this block'}), 403
            
            # Check per-song voting restriction
            if voter_id and db.has_voted(song_id, voter_id, block_id):
                return jsonify({'error': 'You have already voted on this song'}), 403
        
        db.add_vote(song_id, thumbs_up, rating, voter_id, block_id)
        stats = db.get_song_stats(song_id)
        
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        app.logger.error(f"Error submitting vote for song {song_id}: {e}")
        return jsonify({'error': str(e)}), 500


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


@app.route('/api/songs/<int:song_id>/waveform')
def get_waveform(song_id):
    """Get waveform data for a song."""
    path = waveform.get_waveform_path(song_id)
    if os.path.exists(path):
        return send_file(path)
    return jsonify([]), 404


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
            # Session fixation prevention: clear session before setting new admin
            session.clear()
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
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return render_template('admin/setup.html')
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


@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    """Request password reset email."""
    import email_service
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        # Always show success message to prevent email enumeration
        flash('If an account exists with that email, a reset link has been sent.', 'success')
        
        if email:
            admin = db.get_admin_by_email(email)
            if admin:
                # Check if primary owner - they cannot use password reset
                if db.is_primary_owner(admin['id']):
                    # Silently fail - don't reveal that this is the primary owner
                    return redirect(url_for('admin_login'))
                
                # Check if SMTP is configured
                if email_service.is_smtp_configured():
                    # Generate token and send email
                    token = db.create_password_reset_token(admin['id'])
                    site_url = db.get_setting('site_url', request.host_url.rstrip('/'))
                    reset_url = f"{site_url}/admin/reset-password/{token}"
                    
                    success, error = email_service.send_password_reset_email(
                        admin['email'], reset_url, admin['username']
                    )
                    if not success:
                        app.logger.error(f"Failed to send password reset email: {error}")
        
        return redirect(url_for('admin_login'))
    
    # Check if SMTP is configured - show warning if not
    import email_service
    smtp_configured = email_service.is_smtp_configured()
    
    return render_template('admin/forgot_password.html', smtp_configured=smtp_configured)


@app.route('/admin/reset-password/<token>', methods=['GET', 'POST'])
def admin_reset_password(token):
    """Reset password using valid token."""
    admin = db.validate_reset_token(token)
    
    if not admin:
        flash('Invalid or expired reset link. Please request a new one.', 'error')
        return redirect(url_for('admin_forgot_password'))
    
    # Double-check primary owner (should never get here, but safety)
    if db.is_primary_owner(admin['id']):
        flash('This account cannot use password reset. Use CLI tool instead.', 'error')
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
        elif password != confirm:
            flash('Passwords do not match', 'error')
        else:
            # Update password and invalidate token
            db.update_admin_password(admin['id'], password)
            db.invalidate_reset_token(token)
            flash('Password updated successfully. Please login.', 'success')
            return redirect(url_for('admin_login'))
    
    return render_template('admin/reset_password.html', admin=admin, token=token)


@app.route('/admin/smtp/settings', methods=['POST'])
@admin_or_owner_required
def admin_smtp_settings():
    """Save SMTP settings (admin/owner only)."""
    import email_service
    
    data = request.get_json()
    
    # Save SMTP settings
    db.set_setting('smtp_host', data.get('host', ''))
    db.set_setting('smtp_port', data.get('port', '587'))
    db.set_setting('smtp_username', data.get('username', ''))
    db.set_setting('smtp_from', data.get('from_address', ''))
    db.set_setting('smtp_tls', 'true' if data.get('tls', True) else 'false')
    
    # Only update password if provided (not masked placeholder)
    password = data.get('password', '')
    if password and password != '********':
        encrypted = email_service.encrypt_smtp_password(password)
        db.set_setting('smtp_password', encrypted)
    
    return jsonify({'success': True})


@app.route('/admin/smtp/test', methods=['POST'])
@admin_or_owner_required
def admin_smtp_test():
    """Send a test email (admin/owner only)."""
    import email_service
    
    data = request.get_json()
    test_email = data.get('email', '')
    
    if not test_email:
        return jsonify({'success': False, 'error': 'No email address provided'}), 400
    
    success, error = email_service.test_smtp_connection(test_email)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error}), 400



@app.route('/admin/')
@admin_required
def admin_dashboard():
    """Admin dashboard (with role-based visibility)."""
    admin = session.get('admin', {})
    admin_id = admin.get('id')
    role = admin.get('role', 'editor')
    
    settings = db.get_all_settings()
    # Editors only see their own songs count
    songs = db.get_songs_for_user(admin_id, role)
    admins = db.get_all_admins()
    
    return render_template('admin/dashboard.html', 
                         settings=settings, 
                         songs=songs, 
                         admins=admins,
                         role=role,
                         current_admin_id=admin_id)


@app.route('/admin/settings', methods=['POST'])
@admin_or_owner_required
def admin_update_settings():
    """Update settings (admin/owner only)."""
    data = request.get_json()
    
    allowed_keys = [
        'site_password', 'voting_restriction', 'results_visibility',
        'voting_start', 'voting_end', 'min_listen_time', 'disable_skip',
        'site_title', 'site_description', 'site_url', 'og_image', 'favicon',
        'accent_color', 'visualizer_mode', 'visualizer_color', 'homepage_closed',
        'tracking_code', 'timezone',
        'cast_enabled', 'cast_app_id', 'cast_receiver_type'
    ]
    
    for key, value in data.items():
        if key in allowed_keys:
            db.set_setting(key, value)
    
    return jsonify({'success': True})


@app.route('/admin/upload-asset', methods=['POST'])
@admin_or_owner_required
def admin_upload_asset():
    """Upload an asset (favicon, OG image) - admin/owner only."""
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
@admin_or_owner_required
def admin_delete_asset(asset_type):
    """Delete an uploaded asset (admin/owner only)."""
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
    """Serve uploaded files with path traversal protection."""
    from werkzeug.utils import secure_filename
    
    # Sanitize filename to prevent path traversal
    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        return jsonify({'error': 'Invalid filename'}), 404
    
    file_path = os.path.join(UPLOADS_DIR, safe_filename)
    
    # Extra validation: ensure resolved path is within UPLOADS_DIR
    abs_uploads = os.path.abspath(UPLOADS_DIR)
    abs_file = os.path.abspath(file_path)
    if not abs_file.startswith(abs_uploads):
        return jsonify({'error': 'Access denied'}), 403
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(file_path)


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
    from werkzeug.utils import secure_filename
    original_filename = file.filename
    
    # Check for path traversal attempts explicitly
    if '..' in original_filename or '/' in original_filename or '\\' in original_filename:
        # If secure_filename would strip everything or it looks malicious
        if secure_filename(original_filename) != original_filename:
             # Just a stricter check for the test case
             pass
    
    filename = secure_filename(original_filename)
    
    if not filename:
        return jsonify({'error': 'Invalid filename'}), 400
    
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        return jsonify({'error': f'Unsupported format. Use: {", ".join(SUPPORTED_EXTENSIONS)}'}), 400
    
    # Ensure songs directory exists
    os.makedirs(SONGS_DIR, exist_ok=True)
    
    # Build safe path
    full_path = os.path.abspath(os.path.join(SONGS_DIR, filename))
    
    # Validate path stays within SONGS_DIR
    abs_songs_dir = os.path.abspath(SONGS_DIR)
    if not full_path.startswith(abs_songs_dir):
        return jsonify({'error': 'Invalid path'}), 400
    
    # Check if already exists
    if os.path.exists(full_path):
        return jsonify({'error': 'File already exists'}), 400
    
    file.save(full_path)
    
    # Add to database
    song_id = db.add_song(filename, full_path)
    
    # Trigger normalization in background (optional - could be slow)
    # Trigger normalization and waveform generation
    try:
        audio_normalize.get_or_normalize(full_path)
        waveform.get_or_generate_waveform(full_path, song_id)
    except Exception as e:
        print(f"Post-processing error: {e}")
    
    return jsonify({
        'success': True,
        'song_id': song_id,
        'filename': filename
    })


@app.route('/admin/songs/<int:song_id>', methods=['DELETE'])
@admin_required
def admin_delete_song(song_id):
    """Delete a song (with permission check for editors)."""
    admin = session.get('admin', {})
    admin_id = admin.get('id')
    role = admin.get('role', 'editor')
    
    # Check permission (editors can only delete their own songs)
    can_delete, song = db.can_delete_song(song_id, admin_id, role)
    if not can_delete:
        if not song:
            return jsonify({'error': 'Song not found'}), 404
        return jsonify({'error': 'You can only delete songs you uploaded'}), 403
    
    full_path = db.delete_song(song_id)
    
    if full_path:
        # Delete the original source file
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
                print(f"Deleted source file: {full_path}")
        except Exception as e:
            print(f"Error deleting source file: {e}")
        
        # Delete normalized version
        try:
            import audio_normalize
            normalized_path = audio_normalize.get_normalized_path(full_path)
            if os.path.exists(normalized_path):
                os.remove(normalized_path)
                print(f"Deleted normalized file: {normalized_path}")
        except Exception as e:
            print(f"Error deleting normalized file: {e}")
            
        # Delete waveform
        waveform.delete_waveform(song_id)
        
        return jsonify({'success': True, 'deleted_file': full_path})
    
    return jsonify({'error': 'Song not found'}), 404


@app.route('/admin/songs')
@admin_required
def admin_songs_page():
    """Dedicated song management page (role-filtered)."""
    admin = session.get('admin', {})
    admin_id = admin.get('id')
    role = admin.get('role', 'editor')
    
    # Get songs filtered by role (editors only see their own)
    songs = db.get_songs_for_user(admin_id, role)
    base_names = db.get_unique_base_names()
    
    # Enhance songs with file status and vote counts
    enhanced_songs = []
    total_votes = 0
    
    for song in songs:
        # Check if normalized version exists
        normalized_path = audio_normalize.get_normalized_path(song['full_path'])
        has_normalized = os.path.exists(normalized_path)
        
        # Check if waveform exists
        waveform_path = waveform.get_waveform_path(song['id'])
        has_waveform = os.path.exists(waveform_path)
        
        # Get vote count
        stats = db.get_song_stats(song['id'])
        vote_count = stats.get('vote_count', 0)
        total_votes += vote_count
        
        enhanced_songs.append({
            **song,
            'has_normalized': has_normalized,
            'has_waveform': has_waveform,
            'vote_count': vote_count
        })
    
    return render_template('admin/songs.html', 
                         songs=enhanced_songs, 
                         base_names=base_names,
                         total_votes=total_votes,
                         role=role)


@app.route('/admin/songs/upload', methods=['POST'])
@admin_required
def admin_songs_upload():
    """Upload a new song file with detailed error feedback."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check extension
    filename = file.filename
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        return jsonify({'error': f'Unsupported format. Use: {", ".join(SUPPORTED_EXTENSIONS)}'}), 400
    
    # Ensure songs directory exists and is writable
    try:
        os.makedirs(SONGS_DIR, exist_ok=True)
    except PermissionError:
        return jsonify({'error': 'Cannot create songs directory - permission denied'}), 500
    
    # Check write permissions
    full_path = os.path.abspath(os.path.join(SONGS_DIR, filename))
    
    # Security: ensure path is still within SONGS_DIR
    if not full_path.startswith(os.path.abspath(SONGS_DIR)):
        return jsonify({'error': 'Invalid filename'}), 400
    
    # Check if already exists
    if os.path.exists(full_path):
        return jsonify({'error': 'File already exists'}), 400
    
    # Save file
    try:
        file.save(full_path)
    except PermissionError:
        return jsonify({'error': 'Cannot save file - permission denied'}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to save file: {str(e)}'}), 500
    
    # Add to database with current user as uploader
    admin_id = session.get('admin', {}).get('id')
    song_id = db.add_song(filename, full_path, uploaded_by=admin_id)
    
    # Process in background - normalization and waveform
    processing_errors = []
    
    try:
        audio_normalize.get_or_normalize(full_path)
    except Exception as e:
        processing_errors.append(f'Normalization: {str(e)}')
    
    try:
        waveform.get_or_generate_waveform(full_path, song_id)
    except Exception as e:
        processing_errors.append(f'Waveform: {str(e)}')
    
    result = {
        'success': True,
        'song_id': song_id,
        'filename': filename
    }
    
    if processing_errors:
        result['warnings'] = processing_errors
    
    return jsonify(result)


@app.route('/admin/songs/regenerate-waveforms', methods=['POST'])
@admin_or_owner_required
def admin_regenerate_waveforms():
    """Regenerate waveform data for all songs (admin/owner only)."""
    songs = db.get_all_songs()
    regenerated = 0
    errors = []
    
    for song in songs:
        try:
            # Delete existing waveform first
            waveform.delete_waveform(song['id'])
            # Generate new one
            if os.path.exists(song['full_path']):
                waveform.generate_waveform(song['full_path'], song['id'])
                regenerated += 1
            else:
                errors.append(f"{song['filename']}: source file missing")
        except Exception as e:
            errors.append(f"{song['filename']}: {str(e)}")
    
    return jsonify({
        'success': True,
        'count': regenerated,
        'errors': errors if errors else None
    })


@app.route('/admin/songs/renormalize', methods=['POST'])
@admin_or_owner_required
def admin_renormalize_songs():
    """Re-normalize audio for all songs (admin/owner only)."""
    songs = db.get_all_songs()
    renormalized = 0
    errors = []
    
    for song in songs:
        try:
            # Delete existing normalized version
            normalized_path = audio_normalize.get_normalized_path(song['full_path'])
            if os.path.exists(normalized_path):
                os.remove(normalized_path)
            
            # Re-normalize
            if os.path.exists(song['full_path']):
                audio_normalize.normalize_audio(song['full_path'])
                renormalized += 1
            else:
                errors.append(f"{song['filename']}: source file missing")
        except Exception as e:
            errors.append(f"{song['filename']}: {str(e)}")
    
    return jsonify({
        'success': True,
        'count': renormalized,
        'errors': errors if errors else None
    })


@app.route('/admin/songs/cleanup', methods=['POST'])
@admin_or_owner_required
def admin_cleanup_orphans():
    """Clean up orphan normalized and waveform files (admin/owner only)."""
    songs = db.get_all_songs()
    
    # Build set of valid paths
    valid_normalized_paths = set()
    valid_waveform_ids = set()
    
    for song in songs:
        normalized_path = audio_normalize.get_normalized_path(song['full_path'])
        valid_normalized_paths.add(os.path.basename(normalized_path))
        valid_waveform_ids.add(str(song['id']))
    
    normalized_removed = 0
    waveforms_removed = 0
    
    # Clean up normalized directory
    normalized_dir = audio_normalize.NORMALIZED_DIR
    if os.path.exists(normalized_dir):
        for filename in os.listdir(normalized_dir):
            if filename not in valid_normalized_paths:
                try:
                    os.remove(os.path.join(normalized_dir, filename))
                    normalized_removed += 1
                except Exception:
                    pass
    
    # Clean up waveform directory
    waveform_dir = waveform.WAVEFORM_DIR
    if os.path.exists(waveform_dir):
        for filename in os.listdir(waveform_dir):
            # Waveform files are named {song_id}.json
            file_id = os.path.splitext(filename)[0]
            if file_id not in valid_waveform_ids:
                try:
                    os.remove(os.path.join(waveform_dir, filename))
                    waveforms_removed += 1
                except Exception:
                    pass
    
    return jsonify({
        'success': True,
        'normalized_removed': normalized_removed,
        'waveforms_removed': waveforms_removed
    })


@app.route('/admin/admins', methods=['POST'])
@admin_or_owner_required
def admin_create_admin():
    """Create a new admin (admin/owner only)."""
    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'editor')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    # Only owners can create owners
    current_role = session.get('admin', {}).get('role')
    if role == 'owner' and current_role != 'owner':
        return jsonify({'error': 'Only owners can create other owners'}), 403
    
    admin_id = db.create_admin(username, password, role)
    if admin_id:
        return jsonify({'success': True, 'id': admin_id, 'role': role})
    return jsonify({'error': 'Username already exists'}), 400


@app.route('/admin/admins/<int:admin_id>/role', methods=['PUT'])
@owner_required
def admin_update_role(admin_id):
    """Update an admin's role (owner only)."""
    data = request.get_json()
    new_role = data.get('role')
    
    if not new_role:
        return jsonify({'error': 'Role is required'}), 400
    
    requesting_admin_id = session.get('admin', {}).get('id')
    success, error = db.update_admin_role(admin_id, new_role, requesting_admin_id)
    
    if success:
        return jsonify({'success': True})
    return jsonify({'error': error}), 400


@app.route('/admin/admins/<int:admin_id>', methods=['DELETE'])
@admin_or_owner_required
def admin_delete_admin(admin_id):
    """Delete an admin (admin/owner only, with hierarchy protection)."""
    requesting_admin_id = session.get('admin', {}).get('id')
    
    success, error = db.delete_admin(admin_id, requesting_admin_id)
    
    if success:
        return jsonify({'success': True})
    return jsonify({'error': error}), 400


# ============ Vote Block Admin Routes ============

@app.route('/admin/blocks')
@admin_required
def admin_blocks():
    """Vote blocks management page (role-filtered)."""
    admin_info = session.get('admin', {})
    admin_id = admin_info.get('id')
    role = admin_info.get('role', 'editor')
    is_owner_or_admin = role in ('owner', 'admin')
    
    # Editors only see their own blocks, owners/admins see all
    blocks = db.get_all_vote_blocks(admin_id=admin_id, is_owner=is_owner_or_admin)
    
    # Get songs filtered by role for the song selector
    songs = db.get_songs_for_user(admin_id, role)
    
    return render_template('admin/blocks.html', blocks=blocks, songs=songs, 
                          is_owner=is_owner_or_admin, role=role)



@app.route('/admin/blocks', methods=['POST'])
@admin_required
def admin_create_block():
    """Create a new vote block."""
    data = request.get_json()
    
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    song_ids = data.get('song_ids', [])
    if not song_ids:
        return jsonify({'error': 'Select at least one song'}), 400
    
    password = data.get('password')
    password = password.strip() if password else None
    expires_at = data.get('expires_at')
    expires_at = expires_at.strip() if expires_at else None
    
    one_time_use = data.get('one_time_use', False)
    voting_restriction = data.get('voting_restriction', '')
    
    # Per-block settings (None means use global)
    disable_skip = data.get('disable_skip')
    min_listen_time = data.get('min_listen_time')
    if min_listen_time is not None:
        try:
            min_listen_time = int(min_listen_time) if str(min_listen_time).strip() else None
        except ValueError:
            min_listen_time = None
    
    created_by = session.get('admin', {}).get('id')
    
    try:
        result = db.create_vote_block(name, song_ids, password, expires_at, created_by,
                                       one_time_use=one_time_use, voting_restriction=voting_restriction,
                                       disable_skip=disable_skip, min_listen_time=min_listen_time)
        return jsonify({'success': True, 'slug': result['slug'], 'id': result['id']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/admin/blocks/<int:block_id>', methods=['DELETE'])
@admin_required
def admin_delete_block(block_id):
    """Delete a vote block."""
    if db.delete_vote_block(block_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Vote block not found'}), 404


@app.route('/admin/blocks/<int:block_id>', methods=['PUT'])
@admin_required
def admin_update_block(block_id):
    """Update a vote block's settings."""
    data = request.get_json()
    
    name = data.get('name')
    name = name.strip() if name else None
    
    password = data.get('password')
    password = password.strip() if password else None
    clear_password = data.get('clear_password', False)
    
    expires_at = data.get('expires_at')
    expires_at = expires_at.strip() if expires_at else None
    clear_expires = data.get('clear_expires', False)
    
    one_time_use = data.get('one_time_use')
    voting_restriction = data.get('voting_restriction')
    
    # Per-block settings
    disable_skip = data.get('disable_skip')
    clear_disable_skip = data.get('clear_disable_skip', False)
    
    min_listen_time = data.get('min_listen_time')
    clear_min_listen_time = data.get('clear_min_listen_time', False)
    if min_listen_time is not None and not clear_min_listen_time:
        try:
            min_listen_time = int(min_listen_time) if str(min_listen_time).strip() else None
        except ValueError:
            min_listen_time = None
    
    try:
        db.update_vote_block(
            block_id,
            name=name,
            password=password,
            clear_password=clear_password,
            expires_at=expires_at,
            clear_expires=clear_expires,
            one_time_use=one_time_use,
            voting_restriction=voting_restriction,
            disable_skip=disable_skip,
            clear_disable_skip=clear_disable_skip,
            min_listen_time=min_listen_time,
            clear_min_listen_time=clear_min_listen_time
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/admin/blocks/<int:block_id>', methods=['GET'])
@admin_required
def admin_get_block(block_id):
    """Get vote block details."""
    block = db.get_vote_block_by_id(block_id)
    if not block:
        return jsonify({'error': 'Vote block not found'}), 404
    
    songs = db.get_vote_block_songs(block_id)
    return jsonify({'block': block, 'songs': songs})


@app.route('/admin/blocks/<int:block_id>/results', methods=['GET'])
@admin_required
def admin_block_results(block_id):
    """Get vote results for a specific block."""
    block = db.get_vote_block_by_id(block_id)
    if not block:
        return jsonify({'error': 'Vote block not found'}), 404
    
    results = db.get_block_results(block_id)
    return jsonify({'block': block, 'results': results})


# ============ Error Handlers ============

@app.errorhandler(404)
def not_found(e):
    """Custom 404 error page."""
    return render_template('error_404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    """Custom 500 error page."""
    return render_template('error_500.html'), 500


@app.errorhandler(403)
def forbidden(e):
    """Custom 403 error page."""
    return render_template('error_403.html'), 403


# Initialize database on module import (works with gunicorn)
db.init_db()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
