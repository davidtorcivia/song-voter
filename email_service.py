"""
Email service for sending SMTP emails (password reset, etc.)
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from cryptography.fernet import Fernet
import hashlib
import base64

import database as db


def _get_encryption_key():
    """
    Derive a Fernet key from the app's SECRET_KEY.
    Uses SHA256 to get consistent 32 bytes, then base64 encodes for Fernet.
    """
    secret = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    # Fernet requires exactly 32 bytes, base64 encoded
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_smtp_password(password):
    """Encrypt SMTP password for storage."""
    if not password:
        return ''
    fernet = Fernet(_get_encryption_key())
    return fernet.encrypt(password.encode()).decode()


def decrypt_smtp_password(encrypted):
    """Decrypt SMTP password from storage."""
    if not encrypted:
        return ''
    try:
        fernet = Fernet(_get_encryption_key())
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return ''


def get_smtp_config():
    """
    Get SMTP configuration from settings.
    Returns dict with decrypted password.
    """
    return {
        'host': db.get_setting('smtp_host', ''),
        'port': int(db.get_setting('smtp_port', '587') or 587),
        'username': db.get_setting('smtp_username', ''),
        'password': decrypt_smtp_password(db.get_setting('smtp_password', '')),
        'from_address': db.get_setting('smtp_from', ''),
        'tls': db.get_setting('smtp_tls', 'true') == 'true',
    }


def is_smtp_configured():
    """Check if SMTP is properly configured."""
    config = get_smtp_config()
    return bool(config['host'] and config['from_address'])


def send_email(to, subject, body):
    """
    Send an email using configured SMTP settings.
    Returns (success, error_message).
    """
    config = get_smtp_config()
    
    if not config['host']:
        return False, 'SMTP not configured: no host'
    if not config['from_address']:
        return False, 'SMTP not configured: no from address'
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['from_address']
        msg['To'] = to
        
        # Plain text body
        part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(part)
        
        # Connect to SMTP server
        if config['tls']:
            # STARTTLS on port 587
            server = smtplib.SMTP(config['host'], config['port'], timeout=30)
            server.starttls()
        else:
            # Direct SSL on port 465
            server = smtplib.SMTP_SSL(config['host'], config['port'], timeout=30)
        
        # Authenticate if credentials provided
        if config['username'] and config['password']:
            server.login(config['username'], config['password'])
        
        # Send email
        server.sendmail(config['from_address'], [to], msg.as_string())
        server.quit()
        
        return True, None
        
    except smtplib.SMTPAuthenticationError as e:
        return False, f'Authentication failed: {str(e)}'
    except smtplib.SMTPConnectError as e:
        return False, f'Connection failed: {str(e)}'
    except smtplib.SMTPException as e:
        return False, f'SMTP error: {str(e)}'
    except Exception as e:
        return False, f'Error: {str(e)}'


def test_smtp_connection(test_recipient):
    """
    Send a test email to verify SMTP configuration.
    Returns (success, error_message).
    """
    site_title = db.get_setting('site_title', 'Song Voter')
    
    subject = f'Test Email - {site_title}'
    body = f"""-------------------------------------------
            SMTP TEST SUCCESSFUL
-------------------------------------------

This is a test email from {site_title}.

Your SMTP configuration is working correctly.

-------------------------------------------
{site_title}
"""
    
    return send_email(test_recipient, subject, body)


def send_password_reset_email(admin_email, reset_url, admin_username):
    """
    Send a password reset email.
    Returns (success, error_message).
    """
    site_title = db.get_setting('site_title', 'Song Voter')
    
    subject = f'Password Reset - {site_title}'
    body = f"""-------------------------------------------
        PASSWORD RESET REQUEST
-------------------------------------------

A password reset was requested for your account: {admin_username}

Click the link below to reset your password:

{reset_url}

This link expires in 1 hour.

If you did not request this, ignore this email.

-------------------------------------------
{site_title}
"""
    
    return send_email(admin_email, subject, body)
