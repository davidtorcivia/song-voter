"""
Test voting functionality and restrictions.
"""
import pytest
import database as db


def test_submit_vote_success(client, sample_songs):
    """Test successful vote submission."""
    # Reset voting restriction to ensure clean state
    db.set_setting('voting_restriction', 'none')
    
    song = sample_songs[0]
    
    response = client.post(f'/api/songs/{song["id"]}/vote', json={
        'rating': 8,
        'thumbs_up': True
    })
    
    data = response.get_json()
    assert response.status_code == 200
    assert data['success'] is True


def test_submit_vote_missing_data(client, sample_songs):
    """Test vote submission without rating or thumbs_up fails."""
    song = sample_songs[0]
    
    response = client.post(f'/api/songs/{song["id"]}/vote', json={})
    
    assert response.status_code == 400


def test_submit_vote_invalid_rating(client, sample_songs):
    """Test vote submission with invalid rating fails."""
    song = sample_songs[0]
    
    response = client.post(f'/api/songs/{song["id"]}/vote', json={
        'rating': 11,  # Out of range!
        'thumbs_up': True
    })
    
    assert response.status_code == 400


def test_duplicate_vote_prevention_ip(client, sample_songs):
    """Test that duplicate votes from same IP are prevented."""
    # Use a different song than other tests to avoid prior vote conflicts
    song = sample_songs[2]
    
    # Ensure clean state: reset to 'none' first, then set 'ip' 
    # This ensures prior tests' IP restriction doesn't interfere
    db.set_setting('voting_restriction', 'none')
    
    # Clear any prior votes for this song to ensure isolation
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM votes WHERE song_id = ?', (song['id'],))
    conn.commit()
    conn.close()
    
    # Now set IP-based restriction
    db.set_setting('voting_restriction', 'ip')
    
    # First vote should succeed
    response1 = client.post(f'/api/songs/{song["id"]}/vote', json={
        'rating': 8,
        'thumbs_up': True
    })
    assert response1.status_code == 200
    
    # Second vote from same IP should fail
    response2 = client.post(f'/api/songs/{song["id"]}/vote', json={
        'rating': 9,
        'thumbs_up': True
    })
    data = response2.get_json()
    assert response2.status_code == 403
    assert 'already voted' in data.get('error', '').lower()
    
    # Reset voting restriction for other tests
    db.set_setting('voting_restriction', 'none')


def test_get_vote_results(client, sample_songs):
    """Test retrieving vote results."""
    # Reset voting restriction first
    db.set_setting('voting_restriction', 'none')
    
    # Submit a vote first
    song = sample_songs[0]
    client.post(f'/api/songs/{song["id"]}/vote', json={
        'rating': 8,
        'thumbs_up': True
    })
    
    response = client.get('/api/results')
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'results' in data
    assert len(data['results']) > 0
