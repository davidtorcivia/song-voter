"""
Test voting functionality and restrictions.
"""
import pytest
import database as db


def test_submit_vote_success(client, sample_songs):
    """Test successful vote submission."""
    song = sample_songs[0]
    
    response = client.post('/api/vote', json={
        'song_id': song['id'],
        'rating': 8,
        'thumbs_up': True,
        'comment': 'Great song!'
    })
    
    data = response.get_json()
    assert response.status_code == 200
    assert data['success'] is True


def test_submit_vote_missing_song_id(client):
    """Test vote submission without song_id fails."""
    response = client.post('/api/vote', json={
        'rating': 8,
        'thumbs_up': True
    })
    
    assert response.status_code == 400


def test_submit_vote_invalid_rating(client, sample_songs):
    """Test vote submission with invalid rating fails."""
    song = sample_songs[0]
    
    response = client.post('/api/vote', json={
        'song_id': song['id'],
        'rating': 11,  # Out of range!
        'thumbs_up': True
    })
    
    assert response.status_code == 400


def test_duplicate_vote_prevention_ip(client, sample_songs):
    """Test that duplicate votes from same IP are prevented."""
    song = sample_songs[0]
    
    # Set IP-based restriction
    db.set_setting('voting_restriction', 'ip')
    
    # First vote
    response1 = client.post('/api/vote', json={
        'song_id': song['id'],
        'rating': 8,
        'thumbs_up': True
    })
    assert response1.status_code == 200
    
    # Second vote from same IP should fail
    response2 = client.post('/api/vote', json={
        'song_id': song['id'],
        'rating': 9,
        'thumbs_up': True
    })
    data = response2.get_json()
    assert 'already voted' in data.get('error', '').lower()


def test_get_vote_results(client, sample_songs):
    """Test retrieving vote results."""
    # Submit a vote first
    song = sample_songs[0]
    client.post('/api/vote', json={
        'song_id': song['id'],
        'rating': 8,
        'thumbs_up': True
    })
    
    response = client.get('/api/results')
    assert response.status_code == 200
    
    data = response.get_json()
    assert 'results' in data
    assert len(data['results']) > 0
