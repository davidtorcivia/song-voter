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
    
    # Votes table with voter tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER NOT NULL,
            thumbs_up BOOLEAN,
            rating INTEGER CHECK(rating >= 1 AND rating <= 10),
            voter_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (song_id) REFERENCES songs(id)
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
    
    # Initialize default settings if not exist
    default_settings = {
        'results_public': 'true',
        'site_password': '',
        'voting_restriction': 'none'  # none, ip, cookie
    }
    for key, value in default_settings.items():
        cursor.execute(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            (key, value)
        )
    
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


def has_voted(song_id, voter_id):
    """Check if this voter has already voted on this song."""
    if not voter_id:
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id FROM votes WHERE song_id = ? AND voter_id = ?',
        (song_id, voter_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def add_vote(song_id, thumbs_up, rating, voter_id=None):
    """Add a vote for a song."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO votes (song_id, thumbs_up, rating, voter_id) VALUES (?, ?, ?, ?)',
        (song_id, thumbs_up, rating, voter_id)
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
        LEFT JOIN votes v ON s.id = v.song_id
        GROUP BY s.id
        ORDER BY s.base_name, s.filename
    ''')
    
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
            'thumbs_up_pct': round(thumbs_up_pct, 1) if thumbs_up_pct is not None else None
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
