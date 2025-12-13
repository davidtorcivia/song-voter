"""
Pytest configuration and shared fixtures.
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import app as app_module
import database as db


@pytest.fixture
def app():
    """Create and configure a test Flask app."""
    # Create a temporary directory for test data
    test_data_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(test_data_dir, 'test.db')
    
    # Override environment variables
    os.environ['DATA_DIR'] = test_data_dir
    os.environ['DATABASE_PATH'] = test_db_path
    
    # Monkeypatch database path since it's already imported
    old_db_path = db.DATABASE_PATH
    db.DATABASE_PATH = test_db_path
    
    # Create the app
    test_app = app_module.app
    test_app.config.update({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
    })
    
    # Initialize database
    db.init_db()
    
    # Create default admin for tests
    db.create_admin('test@example.com', 'testpass123', 'owner')
    
    yield test_app
    
    # Cleanup
    db.DATABASE_PATH = old_db_path  # Restore original path
    
    # Cleanup
    try:
        os.remove(test_db_path)
        os.rmdir(test_data_dir)
    except:
        pass


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Create an authenticated admin test client."""
    # Login as admin - note: form uses 'username' field, not 'email'
    client.post('/admin/login', data={
        'username': 'test@example.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    
    yield client
    
    # Logout
    client.get('/admin/logout')


@pytest.fixture
def sample_songs(app):
    """Add sample songs to the test database."""
    songs = []
    for i in range(3):
        song_id = db.add_song(
            filename=f'test_song_{i}.mp3',
            full_path=f'/fake/path/test_song_{i}.mp3'
        )
        songs.append(db.get_song_by_id(song_id))
    
    return songs


@pytest.fixture
def vote_block(auth_client, sample_songs):
    """Create a test vote block."""
    song_ids = [s['id'] for s in sample_songs]
    
    response = auth_client.post('/admin/blocks', json={
        'name': 'Test Block',
        'song_ids': song_ids,
        'password': None,
        'expires_at': None,
        'voting_restriction': None
    })
    
    data = response.get_json()
    return db.get_vote_block_by_id(data['id'])
