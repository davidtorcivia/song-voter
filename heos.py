"""
HEOS Device Discovery and Control

HEOS uses:
- SSDP for discovery (port 1900)
- Telnet for control (port 1255)
"""

import socket
import json
import re
import threading
from urllib.parse import urlparse

HEOS_PORT = 1255
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

# Cache discovered devices
_devices_cache = []
_cache_lock = threading.Lock()


def discover_heos_devices(timeout=3):
    """
    Discover HEOS devices on the network using SSDP.
    Returns list of {'name': str, 'host': str, 'pid': str}
    """
    devices = []
    
    # SSDP M-SEARCH for HEOS devices
    ssdp_request = (
        'M-SEARCH * HTTP/1.1\r\n'
        'HOST: 239.255.255.250:1900\r\n'
        'MAN: "ssdp:discover"\r\n'
        'MX: 3\r\n'
        'ST: urn:schemas-denon-com:device:ACT-Denon:1\r\n'
        '\r\n'
    )
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        
        # Send discovery request
        sock.sendto(ssdp_request.encode(), (SSDP_ADDR, SSDP_PORT))
        
        # Collect responses
        hosts_found = set()
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                host = addr[0]
                
                if host not in hosts_found:
                    hosts_found.add(host)
                    # Get device info via HEOS command
                    device_info = get_device_info(host)
                    if device_info:
                        devices.append(device_info)
            except socket.timeout:
                break
                
    except Exception as e:
        print(f"SSDP discovery error: {e}")
    finally:
        sock.close()
    
    # Update cache
    with _cache_lock:
        global _devices_cache
        _devices_cache = devices
    
    return devices


def get_cached_devices():
    """Get cached devices without rediscovery."""
    with _cache_lock:
        return list(_devices_cache)


def send_heos_command(host, command, timeout=5):
    """
    Send a command to a HEOS device via telnet.
    Returns parsed JSON response or None on error.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, HEOS_PORT))
        
        # Send command
        full_command = f"heos://{command}\r\n"
        sock.send(full_command.encode())
        
        # Read response (HEOS sends JSON terminated by \r\n)
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b'\r\n' in response:
                break
        
        sock.close()
        
        # Parse JSON response
        response_str = response.decode('utf-8').strip()
        if response_str:
            return json.loads(response_str)
        return None
        
    except Exception as e:
        print(f"HEOS command error ({host}): {e}")
        return None


def get_device_info(host):
    """Get device info from a HEOS device."""
    response = send_heos_command(host, "player/get_players")
    
    if response and 'payload' in response:
        players = response['payload']
        if players:
            # Return first player on this device
            player = players[0]
            return {
                'name': player.get('name', 'HEOS Device'),
                'host': host,
                'pid': str(player.get('pid', '')),
                'model': player.get('model', ''),
            }
    return None


def get_all_players(host):
    """Get all players from a HEOS device (for groups)."""
    response = send_heos_command(host, "player/get_players")
    
    if response and 'payload' in response:
        return response['payload']
    return []


def play_url(host, pid, url):
    """
    Tell a HEOS device to play a URL.
    Returns True on success, False on error.
    """
    # HEOS play_stream command
    # Format: heos://browse/play_stream?pid={pid}&url={url}
    command = f"browse/play_stream?pid={pid}&url={url}"
    response = send_heos_command(host, command)
    
    if response and 'heos' in response:
        result = response['heos'].get('result', '')
        return result == 'success'
    return False


def set_volume(host, pid, level):
    """Set volume (0-100) on a HEOS device."""
    command = f"player/set_volume?pid={pid}&level={level}"
    response = send_heos_command(host, command)
    return response and response.get('heos', {}).get('result') == 'success'


def stop_playback(host, pid):
    """Stop playback on a HEOS device."""
    command = f"player/set_play_state?pid={pid}&state=stop"
    response = send_heos_command(host, command)
    return response and response.get('heos', {}).get('result') == 'success'
