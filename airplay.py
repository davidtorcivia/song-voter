"""
AirPlay Device Discovery and Control using pyatv

Requires: pip install pyatv
"""

import asyncio
import threading
from typing import List, Dict, Optional

try:
    import pyatv
    PYATV_AVAILABLE = True
except ImportError:
    PYATV_AVAILABLE = False
    print("pyatv not installed - AirPlay support disabled")

# Cache discovered devices
_devices_cache: List[Dict] = []
_cache_lock = threading.Lock()


def is_available() -> bool:
    """Check if pyatv is available."""
    return PYATV_AVAILABLE


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create new loop in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=10)
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop, create one
        return asyncio.run(coro)


async def _discover_devices_async(timeout: int = 5) -> List[Dict]:
    """Async device discovery."""
    if not PYATV_AVAILABLE:
        return []
    
    devices = []
    
    try:
        atvs = await pyatv.scan(asyncio.get_event_loop(), timeout=timeout)
        
        for atv in atvs:
            # Check if AirPlay is supported
            airplay_service = None
            for service in atv.services:
                if service.protocol.name == 'AirPlay':
                    airplay_service = service
                    break
            
            if airplay_service:
                devices.append({
                    'name': atv.name,
                    'address': str(atv.address),
                    'identifier': atv.identifier,
                    'model': atv.device_info.model.name if atv.device_info else 'Unknown',
                })
    except Exception as e:
        print(f"AirPlay discovery error: {e}")
    
    return devices


def discover_airplay_devices(timeout: int = 5) -> List[Dict]:
    """
    Discover AirPlay devices on the network.
    Returns list of {'name': str, 'address': str, 'identifier': str, 'model': str}
    """
    if not PYATV_AVAILABLE:
        return []
    
    devices = _run_async(_discover_devices_async(timeout))
    
    # Update cache
    with _cache_lock:
        global _devices_cache
        _devices_cache = devices
    
    return devices


def get_cached_devices() -> List[Dict]:
    """Get cached devices without rediscovery."""
    with _cache_lock:
        return list(_devices_cache)


async def _stream_url_async(address: str, url: str) -> bool:
    """Stream a URL to an AirPlay device."""
    if not PYATV_AVAILABLE:
        return False
    
    try:
        # Scan for specific device
        atvs = await pyatv.scan(asyncio.get_event_loop(), hosts=[address], timeout=3)
        
        if not atvs:
            print(f"Device not found at {address}")
            return False
        
        config = atvs[0]
        atv = await pyatv.connect(config, asyncio.get_event_loop())
        
        try:
            # Stream the URL
            await atv.stream.stream_url(url)
            return True
        finally:
            atv.close()
            
    except Exception as e:
        print(f"AirPlay stream error: {e}")
        return False


def stream_url(address: str, url: str) -> bool:
    """
    Stream a URL to an AirPlay device.
    Returns True on success, False on error.
    """
    if not PYATV_AVAILABLE:
        return False
    
    return _run_async(_stream_url_async(address, url))


async def _stop_playback_async(address: str) -> bool:
    """Stop playback on an AirPlay device."""
    if not PYATV_AVAILABLE:
        return False
    
    try:
        atvs = await pyatv.scan(asyncio.get_event_loop(), hosts=[address], timeout=3)
        
        if not atvs:
            return False
        
        config = atvs[0]
        atv = await pyatv.connect(config, asyncio.get_event_loop())
        
        try:
            await atv.remote_control.stop()
            return True
        finally:
            atv.close()
            
    except Exception as e:
        print(f"AirPlay stop error: {e}")
        return False


def stop_playback(address: str) -> bool:
    """Stop playback on an AirPlay device."""
    if not PYATV_AVAILABLE:
        return False
    
    return _run_async(_stop_playback_async(address))
