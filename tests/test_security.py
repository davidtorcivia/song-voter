"""
Security tests for path traversal, headers, and authentication.
"""
import pytest
import os


def test_upload_path_traversal_blocked(client):
    """Test that path traversal attempts in uploads are blocked."""
    # Attempt path traversal with various payloads
    payloads = [
        '../../../etc/passwd',
        '..\\..\\..\\windows\\system32\\config\\sam',
        '....//....//....//etc/passwd',
        '%2e%2e%2f%2e%2e%2f',
    ]
    
    for payload in payloads:
        response = client.get(f'/uploads/{payload}')
        # Should return 404 (not found) not 200 with file contents
        assert response.status_code in [403, 404], f"Path traversal not blocked for: {payload}"


def test_security_headers_present(client):
    """Test that security headers are present in responses."""
    response = client.get('/')
    
    assert 'X-Content-Type-Options' in response.headers
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    
    assert 'X-Frame-Options' in response.headers
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    
    assert 'X-XSS-Protection' in response.headers
    assert '1' in response.headers['X-XSS-Protection']


def test_admin_password_length_requirement(client):
    """Test that admin setup requires minimum password length."""
    # Only works if no admins exist - skip if admins already exist
    response = client.get('/admin/setup')
    if response.status_code == 302:
        pytest.skip("Admins already exist, can't test setup")
    
    # Try short password
    response = client.post('/admin/setup', data={
        'username': 'testadmin',
        'password': 'short'  # Too short
    })
    
    # Should not redirect (stays on setup page with error)
    assert response.status_code == 200 or b'8 characters' in response.data


def test_invalid_filename_in_upload_blocked(auth_client):
    """Test that invalid filenames are rejected during upload."""
    from io import BytesIO
    
    # Attempt to upload with path traversal filename
    # werkzeug secure_filename strips path components, making filenames like '../' become empty
    data = {
        'file': (BytesIO(b'fake audio data'), '../../malicious.mp3')
    }
    response = auth_client.post('/admin/upload', data=data, content_type='multipart/form-data')
    
    # Should be rejected - either 400 for invalid filename or unsupported format
    assert response.status_code == 400


def test_session_cleared_on_login(client):
    """Test that session is cleared on login to prevent fixation."""
    import database as db
    
    # Set some session data before login
    with client.session_transaction() as sess:
        sess['evil_data'] = 'should_be_cleared'
    
    # Login
    response = client.post('/admin/login', data={
        'username': 'test@example.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    
    # Check session was cleared
    with client.session_transaction() as sess:
        assert 'evil_data' not in sess


def test_admin_required_redirect(client):
    """Test that protected routes redirect to login."""
    protected_routes = [
        '/admin/',
        '/admin/blocks',
    ]
    
    for route in protected_routes:
        response = client.get(route)
        assert response.status_code == 302
        assert '/admin/login' in response.location or 'login' in response.location.lower(), \
            f"Route {route} should redirect to login"
