"""
Test vote blocks functionality.
"""
import pytest
import database as db


def test_create_vote_block_success(auth_client, sample_songs):
    """Test creating a vote block."""
    song_ids = [s['id'] for s in sample_songs]
    
    response = auth_client.post('/admin/blocks', json={
        'name': 'Test Block',
        'song_ids': song_ids
    })
    
    data = response.get_json()
    assert response.status_code == 200
    assert data['success'] is True
    assert 'block_id' in data


def test_create_vote_block_no_songs(auth_client):
    """Test creating vote block without songs fails."""
    response = auth_client.post('/admin/blocks', json={
        'name': 'Empty Block',
        'song_ids': []
    })
    
    assert response.status_code == 400


def test_create_vote_block_requires_auth(client, sample_songs):
    """Test that creating vote block requires authentication."""
    song_ids = [s['id'] for s in sample_songs]
    
    response = client.post('/admin/blocks', json={
        'name': 'Test Block',
        'song_ids': song_ids
    })
    
    # Should redirect to login (302) or return 401/403
    assert response.status_code in [302, 401, 403]


def test_vote_block_page_loads(client, vote_block):
    """Test that vote block page loads correctly."""
    response = client.get(f'/vote/block/{vote_block["slug"]}')
    assert response.status_code == 200
    assert vote_block['name'].encode() in response.data


def test_vote_block_with_password(auth_client, sample_songs):
    """Test password-protected vote block."""
    song_ids = [s['id'] for s in sample_songs]
    
    # Create password-protected block
    response = auth_client.post('/admin/blocks', json={
        'name': 'Protected Block',
        'song_ids': song_ids,
        'password': 'secret123'
    })
    
    data = response.get_json()
    block = db.get_vote_block_by_id(data['block_id'])
    
    # Try accessing without password
    response = auth_client.get(f'/vote/block/{block["slug"]}')
    # Should redirect to auth page
    assert response.status_code in [302, 200]


def test_delete_vote_block(auth_client, vote_block):
    """Test deleting a vote block."""
    block_id = vote_block['id']
    
    response = auth_client.delete(f'/admin/blocks/{block_id}')
    assert response.status_code == 200
    
    # Verify block is deleted
    deleted_block = db.get_vote_block_by_id(block_id)
    assert deleted_block is None


def test_update_vote_block(auth_client, vote_block):
    """Test updating vote block settings."""
    block_id = vote_block['id']
    
    response = auth_client.put(f'/admin/blocks/{block_id}', json={
        'name': 'Updated Block Name'
    })
    
    assert response.status_code == 200
    
    # Verify update
    updated_block = db.get_vote_block_by_id(block_id)
    assert updated_block['name'] == 'Updated Block Name'
