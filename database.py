import sqlite3
import os
import hashlib
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_PATH = os.environ.get('DATABASE_PATH', 'data/song_voter.db')


def get_db():
    """Get database connection."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Songs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            base_name TEXT NOT NULL,
            full_path TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Votes table with voter tracking and optional block association
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER NOT NULL,
            thumbs_up BOOLEAN,
            rating INTEGER CHECK(rating >= 1 AND rating <= 10),
            voter_id TEXT,
            block_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (song_id) REFERENCES songs(id),
            FOREIGN KEY (block_id) REFERENCES vote_blocks(id) ON DELETE SET NULL
        )
    ''')
    
    # Settings table (key-value store)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Admin users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Vote blocks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vote_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            expires_at TIMESTAMP,
            one_time_use INTEGER DEFAULT 0,
            voting_restriction TEXT DEFAULT '',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES admins(id)
        )
    ''')
    
    # Vote block songs (many-to-many)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vote_block_songs (
            block_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            PRIMARY KEY (block_id, song_id),
            FOREIGN KEY (block_id) REFERENCES vote_blocks(id) ON DELETE CASCADE,
            FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
        )
    ''')
    
    # Initialize default settings if not exist
    default_settings = {
        # Access
        'site_password': '',
        'voting_restriction': 'none',  # none, ip, cookie
        
        # Results visibility: hidden, until_voting_ends, public
        'results_visibility': 'public',
        
        # Voting time window (ISO format, empty = no limit)
        'voting_start': '',
        'voting_end': '',
        
        # Minimum listen time in seconds
        'min_listen_time': '20',
        
        # Disable skip button
        'disable_skip': 'false',
        
        # Branding
        'site_title': 'Song Voter',
        'site_description': 'Vote on your favorite song versions',
        'site_url': '',
        'og_image': '',  # URL or uploaded path
        'favicon': '',   # URL or uploaded path
        
        # UI Customization
        'accent_color': '#ffffff',  # Accent color for waveform, etc.
        'visualizer_mode': 'bars',  # bars, wave, or both
        'visualizer_color': '',  # Empty = use default VU green, otherwise hex color
        
        # Homepage control
        'homepage_closed': 'false',  # When true, homepage shows only title/description
    }
    for key, value in default_settings.items():
        cursor.execute(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            (key, value)
        )
    
    # Migration: Add voter_id column to votes table if it doesn't exist  
    cursor.execute("PRAGMA table_info(votes)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'voter_id' not in columns:
        cursor.execute("ALTER TABLE votes ADD COLUMN voter_id TEXT")
        print("Migration: Added voter_id column to votes table")
    if 'block_id' not in columns:
        cursor.execute("ALTER TABLE votes ADD COLUMN block_id INTEGER")
        print("Migration: Added block_id column to votes table")
    
    # Migration: Add new columns to vote_blocks table
    cursor.execute("PRAGMA table_info(vote_blocks)")
    block_columns = [col[1] for col in cursor.fetchall()]
    if 'one_time_use' not in block_columns:
        cursor.execute("ALTER TABLE vote_blocks ADD COLUMN one_time_use INTEGER DEFAULT 0")
        print("Migration: Added one_time_use column to vote_blocks table")
    if 'voting_restriction' not in block_columns:
        cursor.execute("ALTER TABLE vote_blocks ADD COLUMN voting_restriction TEXT DEFAULT ''")
        print("Migration: Added voting_restriction column to vote_blocks table")
    
    # Create initial admin from environment if specified
    admin_user = os.environ.get('ADMIN_USER')
    admin_pass = os.environ.get('ADMIN_PASS')
    if admin_user and admin_pass:
        try:
            cursor.execute(
                'INSERT OR IGNORE INTO admins (username, password_hash) VALUES (?, ?)',
                (admin_user, generate_password_hash(admin_pass))
            )
        except sqlite3.IntegrityError:
            pass  # Admin already exists
    
    conn.commit()
    conn.close()


def parse_base_name(filename):
    """
    Extract base name from filename, removing version suffixes like (1), (2), etc.
    Example: "The Runoff (1).wav" -> "The Runoff"
    """
    import re
    # Remove extension
    name = os.path.splitext(filename)[0]
    # Remove trailing version numbers like (1), (2), etc.
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    return name.strip()


# ============ Settings ============

def get_setting(key, default=None):
    """Get a setting value."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    """Set a setting value."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        (key, value)
    )
    conn.commit()
    conn.close()


def get_all_settings():
    """Get all settings as a dict."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    return settings


# ============ Admin Users ============

def create_admin(username, password):
    """Create a new admin user."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO admins (username, password_hash) VALUES (?, ?)',
            (username, generate_password_hash(password))
        )
        conn.commit()
        admin_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        admin_id = None  # Username already exists
    conn.close()
    return admin_id


def verify_admin(username, password):
    """Verify admin credentials. Returns admin dict or None."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, password_hash FROM admins WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row and check_password_hash(row['password_hash'], password):
        return {'id': row['id'], 'username': row['username']}
    return None


def get_all_admins():
    """Get all admin users (without passwords)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, created_at FROM admins')
    admins = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return admins


def delete_admin(admin_id):
    """Delete an admin user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE id = ?', (admin_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def admin_count():
    """Get number of admins."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM admins')
    count = cursor.fetchone()['count']
    conn.close()
    return count


def get_first_admin():
    """Get the first (owner) admin by lowest ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM admins ORDER BY id ASC LIMIT 1')
    row = cursor.fetchone()
    admin = dict(row) if row else None
    conn.close()
    return admin


# ============ Songs ============

def add_song(filename, full_path):
    """Add a song to the database."""
    conn = get_db()
    cursor = conn.cursor()
    
    base_name = parse_base_name(filename)
    
    try:
        cursor.execute(
            'INSERT INTO songs (filename, base_name, full_path) VALUES (?, ?, ?)',
            (filename, base_name, full_path)
        )
        conn.commit()
        song_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        # Song already exists
        cursor.execute('SELECT id FROM songs WHERE full_path = ?', (full_path,))
        row = cursor.fetchone()
        song_id = row['id'] if row else None
    
    conn.close()
    return song_id


def delete_song(song_id):
    """Delete a song and its votes."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get the song info first for cleanup
    cursor.execute('SELECT full_path FROM songs WHERE id = ?', (song_id,))
    song = cursor.fetchone()
    
    if song:
        # Delete votes first
        cursor.execute('DELETE FROM votes WHERE song_id = ?', (song_id,))
        # Delete song
        cursor.execute('DELETE FROM songs WHERE id = ?', (song_id,))
        conn.commit()
        conn.close()
        return song['full_path']
    
    conn.close()
    return None


def get_all_songs():
    """Get all songs from the database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, filename, base_name, full_path FROM songs ORDER BY base_name, filename')
    songs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return songs


def get_songs_by_base_name(base_name):
    """Get all songs with a specific base name."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, filename, base_name, full_path FROM songs WHERE base_name = ?',
        (base_name,)
    )
    songs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return songs


def get_unique_base_names():
    """Get all unique base names."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT base_name FROM songs ORDER BY base_name')
    names = [row['base_name'] for row in cursor.fetchall()]
    conn.close()
    return names


def get_song_by_id(song_id):
    """Get a song by its ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, filename, base_name, full_path FROM songs WHERE id = ?', (song_id,))
    row = cursor.fetchone()
    song = dict(row) if row else None
    conn.close()
    return song


# ============ Voting ============

def get_voter_id(request):
    """Generate a voter ID from request (IP or cookie hash)."""
    restriction = get_setting('voting_restriction', 'none')
    
    if restriction == 'ip':
        # Use IP address
        return hashlib.md5(request.remote_addr.encode()).hexdigest()
    elif restriction == 'cookie':
        # Use session ID or cookie
        from flask import session
        if 'voter_id' not in session:
            import uuid
            session['voter_id'] = str(uuid.uuid4())
        return session['voter_id']
    
    return None  # No restriction


def has_voted(song_id, voter_id, block_id=None):
    """Check if this voter has already voted on this song (optionally in a specific block)."""
    if not voter_id:
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    if block_id:
        cursor.execute(
            'SELECT id FROM votes WHERE song_id = ? AND voter_id = ? AND block_id = ?',
            (song_id, voter_id, block_id)
        )
    else:
        cursor.execute(
            'SELECT id FROM votes WHERE song_id = ? AND voter_id = ?',
            (song_id, voter_id)
        )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def add_vote(song_id, thumbs_up, rating, voter_id=None, block_id=None):
    """Add a vote for a song (optionally associated with a vote block)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO votes (song_id, thumbs_up, rating, voter_id, block_id) VALUES (?, ?, ?, ?, ?)',
        (song_id, thumbs_up, rating, voter_id, block_id)
    )
    conn.commit()
    conn.close()


def get_song_stats(song_id):
    """Get aggregate stats for a song."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as vote_count,
            AVG(rating) as avg_rating,
            SUM(CASE WHEN thumbs_up = 1 THEN 1 ELSE 0 END) as thumbs_up_count,
            SUM(CASE WHEN thumbs_up = 0 THEN 1 ELSE 0 END) as thumbs_down_count
        FROM votes 
        WHERE song_id = ?
    ''', (song_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row and row['vote_count'] > 0:
        total_thumbs = row['thumbs_up_count'] + row['thumbs_down_count']
        thumbs_up_pct = (row['thumbs_up_count'] / total_thumbs * 100) if total_thumbs > 0 else None
        return {
            'vote_count': row['vote_count'],
            'avg_rating': round(row['avg_rating'], 2) if row['avg_rating'] else None,
            'thumbs_up_pct': round(thumbs_up_pct, 1) if thumbs_up_pct is not None else None
        }
    return {'vote_count': 0, 'avg_rating': None, 'thumbs_up_pct': None}


def get_all_results():
    """Get aggregate results for all songs."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Using SQLite formula for variance: E[X²] - E[X]² 
    # stdev = sqrt(variance)
    cursor.execute('''
        SELECT 
            s.id,
            s.filename,
            s.base_name,
            COUNT(v.id) as vote_count,
            AVG(v.rating) as avg_rating,
            SUM(CASE WHEN v.thumbs_up = 1 THEN 1 ELSE 0 END) as thumbs_up_count,
            SUM(CASE WHEN v.thumbs_up = 0 THEN 1 ELSE 0 END) as thumbs_down_count,
            AVG(v.rating * v.rating) as avg_rating_squared
        FROM songs s
        LEFT JOIN votes v ON s.id = v.song_id
        GROUP BY s.id
        ORDER BY s.base_name, s.filename
    ''')
    
    results = []
    for row in cursor.fetchall():
        total_thumbs = (row['thumbs_up_count'] or 0) + (row['thumbs_down_count'] or 0)
        thumbs_up_pct = (row['thumbs_up_count'] / total_thumbs * 100) if total_thumbs > 0 else None
        
        # Calculate rating variance and stdev
        avg_rating = row['avg_rating']
        avg_rating_sq = row['avg_rating_squared']
        rating_stdev = None
        agreement_score = None
        is_controversial = False
        
        if avg_rating is not None and avg_rating_sq is not None and row['vote_count'] >= 2:
            # Variance = E[X²] - E[X]²
            variance = avg_rating_sq - (avg_rating ** 2)
            if variance > 0:
                import math
                rating_stdev = math.sqrt(variance)
                # Agreement score: 1 - (stdev / max_possible_stdev)
                # Max stdev for 1-10 scale is 4.5 (all votes at 1 and 10)
                agreement_score = max(0, 1 - (rating_stdev / 4.5)) * 100
                # Controversial: low agreement AND mixed thumbs
                if agreement_score < 50 and thumbs_up_pct and 30 <= thumbs_up_pct <= 70:
                    is_controversial = True
            else:
                # Perfect agreement (all same rating)
                rating_stdev = 0
                agreement_score = 100
        
        results.append({
            'id': row['id'],
            'filename': row['filename'],
            'base_name': row['base_name'],
            'vote_count': row['vote_count'],
            'avg_rating': round(avg_rating, 2) if avg_rating else None,
            'thumbs_up_pct': round(thumbs_up_pct, 1) if thumbs_up_pct is not None else None,
            'rating_stdev': round(rating_stdev, 2) if rating_stdev is not None else None,
            'agreement_score': round(agreement_score, 0) if agreement_score is not None else None,
            'is_controversial': is_controversial
        })
    
    conn.close()
    return results


def clear_all_data():
    """Clear all songs and votes (for rescanning)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM votes')
    cursor.execute('DELETE FROM songs')
    conn.commit()
    conn.close()


# ============ Vote Blocks ============

def generate_block_slug():
    """Generate a unique slug for a vote block."""
    import secrets
    return secrets.token_urlsafe(8)[:12]  # 12 char URL-safe slug


def create_vote_block(name, song_ids, password=None, expires_at=None, created_by=None, 
                       one_time_use=False, voting_restriction=''):
    """Create a new vote block with selected songs."""
    conn = get_db()
    cursor = conn.cursor()
    
    slug = generate_block_slug()
    password_hash = generate_password_hash(password) if password else None
    
    try:
        cursor.execute('''
            INSERT INTO vote_blocks (name, slug, password_hash, expires_at, created_by, one_time_use, voting_restriction)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, slug, password_hash, expires_at, created_by, 1 if one_time_use else 0, voting_restriction))
        
        block_id = cursor.lastrowid
        
        # Add songs to block
        for song_id in song_ids:
            cursor.execute('''
                INSERT OR IGNORE INTO vote_block_songs (block_id, song_id)
                VALUES (?, ?)
            ''', (block_id, song_id))
        
        conn.commit()
    except Exception as e:
        conn.close()
        raise e
    
    conn.close()
    return {'id': block_id, 'slug': slug}


def get_vote_block_by_slug(slug):
    """Get a vote block by its slug."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT vb.*, a.username as creator_name
        FROM vote_blocks vb
        LEFT JOIN admins a ON vb.created_by = a.id
        WHERE vb.slug = ?
    ''', (slug,))
    row = cursor.fetchone()
    block = dict(row) if row else None
    conn.close()
    return block


def get_vote_block_by_id(block_id):
    """Get a vote block by its ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT vb.*, a.username as creator_name
        FROM vote_blocks vb
        LEFT JOIN admins a ON vb.created_by = a.id
        WHERE vb.id = ?
    ''', (block_id,))
    row = cursor.fetchone()
    block = dict(row) if row else None
    conn.close()
    return block


def get_vote_block_songs(block_id):
    """Get all songs in a vote block."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.id, s.filename, s.base_name, s.full_path
        FROM songs s
        JOIN vote_block_songs vbs ON s.id = vbs.song_id
        WHERE vbs.block_id = ?
        ORDER BY s.base_name, s.filename
    ''', (block_id,))
    songs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return songs


def get_all_vote_blocks(admin_id=None, is_owner=False):
    """Get all vote blocks with song counts. Filters by admin unless owner."""
    conn = get_db()
    cursor = conn.cursor()
    
    if admin_id and not is_owner:
        # Non-owner admins only see their own blocks
        cursor.execute('''
            SELECT vb.*, a.username as creator_name,
                   (SELECT COUNT(*) FROM vote_block_songs WHERE block_id = vb.id) as song_count,
                   (SELECT COUNT(*) FROM votes WHERE block_id = vb.id) as vote_count
            FROM vote_blocks vb
            LEFT JOIN admins a ON vb.created_by = a.id
            WHERE vb.created_by = ?
            ORDER BY vb.created_at DESC
        ''', (admin_id,))
    else:
        # Owner sees all blocks
        cursor.execute('''
            SELECT vb.*, a.username as creator_name,
                   (SELECT COUNT(*) FROM vote_block_songs WHERE block_id = vb.id) as song_count,
                   (SELECT COUNT(*) FROM votes WHERE block_id = vb.id) as vote_count
            FROM vote_blocks vb
            LEFT JOIN admins a ON vb.created_by = a.id
            ORDER BY vb.created_at DESC
        ''')
    
    blocks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return blocks


def delete_vote_block(block_id):
    """Delete a vote block."""
    conn = get_db()
    cursor = conn.cursor()
    # Songs association is deleted by CASCADE
    cursor.execute('DELETE FROM vote_blocks WHERE id = ?', (block_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def verify_block_password(block, password):
    """Verify a vote block password."""
    if not block or not block.get('password_hash'):
        return True  # No password required
    return check_password_hash(block['password_hash'], password)


def is_block_expired(block):
    """Check if a vote block has expired."""
    if not block or not block.get('expires_at'):
        return False
    expires_at = block['expires_at']
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    return datetime.now() > expires_at


def has_voted_in_block(voter_id, block_id):
    """Check if this voter has voted on any song in this block (for one-time-use)."""
    if not voter_id or not block_id:
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM votes WHERE voter_id = ? AND block_id = ? LIMIT 1',
        (voter_id, block_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_block_results(block_id):
    """Get aggregate results for songs in a specific vote block."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            s.id,
            s.filename,
            s.base_name,
            COUNT(v.id) as vote_count,
            AVG(v.rating) as avg_rating,
            SUM(CASE WHEN v.thumbs_up = 1 THEN 1 ELSE 0 END) as thumbs_up_count,
            SUM(CASE WHEN v.thumbs_up = 0 THEN 1 ELSE 0 END) as thumbs_down_count
        FROM songs s
        JOIN vote_block_songs vbs ON s.id = vbs.song_id
        LEFT JOIN votes v ON s.id = v.song_id AND v.block_id = ?
        WHERE vbs.block_id = ?
        GROUP BY s.id
        ORDER BY s.base_name, s.filename
    ''', (block_id, block_id))
    
    results = []
    for row in cursor.fetchall():
        total_thumbs = (row['thumbs_up_count'] or 0) + (row['thumbs_down_count'] or 0)
        thumbs_up_pct = (row['thumbs_up_count'] / total_thumbs * 100) if total_thumbs > 0 else None
        
        results.append({
            'id': row['id'],
            'filename': row['filename'],
            'base_name': row['base_name'],
            'vote_count': row['vote_count'],
            'avg_rating': round(row['avg_rating'], 2) if row['avg_rating'] else None,
            'thumbs_up_pct': round(thumbs_up_pct, 1) if thumbs_up_pct is not None else None,
        })
    
    conn.close()
    return results
