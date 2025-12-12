"""
Test public routes and basic functionality.
"""
import pytest


def test_index_page(client):
    """Test that index page loads."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Song Voter' in response.data or b'song' in response.data.lower()


def test_results_page(client):
    """Test that results page loads."""
    response = client.get('/results')
    assert response.status_code == 200


def test_help_page(client):
    """Test that help page loads."""
    response = client.get('/help')
    assert response.status_code == 200


def test_404_page(client):
    """Test custom 404 error page."""
    response = client.get('/nonexistent-page')
    assert response.status_code == 404
    assert b'void' in response.data.lower() or b'404' in response.data


def test_cast_receiver_page(client):
    """Test that cast receiver page loads."""
    response = client.get('/cast-receiver')
    assert response.status_code == 200
    assert b'cast' in response.data.lower()


def test_play_page_missing_song(client):
    """Test play page with non-existent song returns 404."""
    response = client.get('/play/nonexistent-slug')
    assert response.status_code == 404
