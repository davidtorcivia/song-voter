"""
Audio Loudness Normalization using pydub

Normalizes audio files to a target loudness level to enable
fair A/B comparison without volume bias.

Caches normalized files as high-quality MP3 (320kbps) for efficient streaming.
"""

import os
import hashlib
from pathlib import Path

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("pydub not installed - loudness normalization disabled")

# Target loudness in dBFS (decibels relative to full scale)
# -14 dBFS is common for streaming services
TARGET_DBFS = -14.0

# Cache directory for normalized files
NORMALIZED_DIR = os.environ.get('NORMALIZED_DIR', 'normalized')

# Output format settings
OUTPUT_FORMAT = 'mp3'
OUTPUT_BITRATE = '320k'  # High quality MP3


def ensure_normalized_dir():
    """Create normalized directory if it doesn't exist."""
    os.makedirs(NORMALIZED_DIR, exist_ok=True)


def get_normalized_path(original_path):
    """
    Get the path for a normalized version of a file.
    Uses hash of original path to create unique filename.
    """
    # Create hash of original path for unique filename
    path_hash = hashlib.md5(original_path.encode()).hexdigest()[:12]
    original_name = Path(original_path).stem
    return os.path.join(NORMALIZED_DIR, f"{original_name}_{path_hash}_norm.{OUTPUT_FORMAT}")


def is_normalized(original_path):
    """Check if a normalized version exists and is up to date."""
    normalized_path = get_normalized_path(original_path)
    
    if not os.path.exists(normalized_path):
        return False
    
    # Check if original is newer than normalized
    orig_mtime = os.path.getmtime(original_path)
    norm_mtime = os.path.getmtime(normalized_path)
    
    return norm_mtime > orig_mtime


def normalize_audio(input_path, output_path=None, target_dbfs=TARGET_DBFS):
    """
    Normalize audio file to target loudness using simple gain adjustment.
    
    Args:
        input_path: Path to original audio file
        output_path: Path for normalized output (auto-generated if None)
        target_dbfs: Target loudness in dBFS (default -14)
    
    Returns:
        Path to normalized file, or original path if normalization failed
    """
    if not PYDUB_AVAILABLE:
        return input_path
    
    if output_path is None:
        output_path = get_normalized_path(input_path)
    
    ensure_normalized_dir()
    
    try:
        print(f"Normalizing: {Path(input_path).name}")
        
        # Load audio (pydub auto-detects format)
        audio = AudioSegment.from_file(input_path)
        
        # Calculate current loudness (RMS-based dBFS)
        current_dbfs = audio.dBFS
        
        # Calculate gain needed
        gain_db = target_dbfs - current_dbfs
        
        # Apply simple gain adjustment (no limiting/compression)
        # Clamp gain to prevent extreme adjustments
        gain_db = max(-20, min(20, gain_db))
        audio = audio + gain_db
        
        # Export as high-quality MP3
        audio.export(
            output_path, 
            format=OUTPUT_FORMAT,
            bitrate=OUTPUT_BITRATE,
            parameters=["-q:a", "0"]  # Highest quality VBR as fallback
        )
        
        print(f"  -> Cached: {Path(output_path).name} (gain: {gain_db:+.1f} dB)")
        return output_path
        
    except Exception as e:
        print(f"Normalization failed for {input_path}: {e}")
        return input_path


def get_or_normalize(original_path):
    """
    Get normalized version of audio file, creating it if needed.
    
    Returns path to normalized file (or original if normalization unavailable).
    """
    if not PYDUB_AVAILABLE:
        return original_path
    
    if is_normalized(original_path):
        return get_normalized_path(original_path)
    
    return normalize_audio(original_path)


def normalize_all_in_directory(directory):
    """
    Pre-normalize all audio files in a directory.
    Useful for batch processing during scan.
    
    Returns dict mapping original paths to normalized paths.
    """
    if not PYDUB_AVAILABLE:
        return {}
    
    SUPPORTED_EXTENSIONS = ('.wav', '.mp3', '.flac', '.m4a', '.ogg')
    
    ensure_normalized_dir()
    results = {}
    
    for filename in os.listdir(directory):
        if filename.lower().endswith(SUPPORTED_EXTENSIONS):
            original_path = os.path.abspath(os.path.join(directory, filename))
            
            if not is_normalized(original_path):
                normalized_path = normalize_audio(original_path)
            else:
                normalized_path = get_normalized_path(original_path)
            
            results[original_path] = normalized_path
    
    return results
