import sqlite3
import os
from datetime import datetime

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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            base_name TEXT NOT NULL,
            full_path TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER NOT NULL,
            thumbs_up BOOLEAN,
            rating INTEGER CHECK(rating >= 1 AND rating <= 10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (song_id) REFERENCES songs(id)
        )
    ''')
    
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
    # Remove trailing numbers without parentheses (e.g., "Song 2" -> "Song" only if it looks like a version)
    # Being conservative here - only remove if it's clearly a version pattern
    return name.strip()


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


def add_vote(song_id, thumbs_up, rating):
    """Add a vote for a song."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO votes (song_id, thumbs_up, rating) VALUES (?, ?, ?)',
        (song_id, thumbs_up, rating)
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
