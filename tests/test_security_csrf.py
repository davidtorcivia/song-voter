import pytest
from app import app, db
import os

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = True  # Enable CSRF for testing
    with app.test_client() as client:
        with app.app_context():
            db.init_db()
        yield client

def test_csrf_protection_active(client):
    """Test that POST requests without CSRF token are rejected."""
    # Try admin login without token
    response = client.post('/admin/login', data={'username': 'admin', 'password': 'password'})
    assert response.status_code == 400 or b'The CSRF token is missing' in response.data

def test_csrf_token_in_meta(client):
    """Test that CSRF token is present in meta tag on index page."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'name="csrf-token"' in response.data

def test_path_traversal_protection(client):
    """Test that path traversal attempts are blocked."""
    # Assuming we have a song with ID 1 (mocking might be better but for integration test this works if db populated, 
    # but since db is fresh fixture, we might need to add one or just rely on 404 vs 403 logic if applicable).
    
    # We can try to hit the endpoint with a mock or check the logic directly if possible.
    # But since we hardened the actual function, let's try to pass a malicious path if we can insert a song.
    
    # Insert a malicious song entry manually into DB (in memory for test)
    with app.app_context():
        import sqlite3
        import time
        print(f"DEBUG: Using DB at {db.DATABASE_PATH}")
        conn = db.get_db()
        cursor = conn.cursor()
        # Insert a song pointing to a system file - use unique name
        timestamp = int(time.time())
        try:
            fake_path = f'/etc/passwd_{timestamp}' if os.name != 'nt' else f'C:\\Windows\\win_{timestamp}.ini'
            cursor.execute("INSERT INTO songs (filename, base_name, full_path, slug, uploaded_by) VALUES (?, ?, ?, ?, ?)",
                           (f'hack_{timestamp}.mp3', f'hack_{timestamp}', fake_path, f'hack-{timestamp}', 1))
            conn.commit()
            song_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.rollback()
            # If it already exists (e.g. from previous run if db wasn't cleared), try to get it
            cursor.execute("SELECT id FROM songs WHERE filename LIKE 'hack_%'")
            row = cursor.fetchone()
            if row:
                song_id = row['id']
            else:
                raise
        finally:
            conn.close()

    # Try to access it
    # Note: the endpoint checks if file starts with allowed dirs.
    response = client.get(f'/api/songs/{song_id}/audio')
    assert response.status_code == 403  # Should be forbidden due to path check

def test_security_headers(client):
    """Test that security headers are present."""
    response = client.get('/')
    headers = response.headers
    assert 'Content-Security-Policy' in headers
    assert 'Strict-Transport-Security' in headers
    assert 'X-Content-Type-Options' in headers
    assert 'X-Frame-Options' in headers
