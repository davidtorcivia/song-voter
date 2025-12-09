"""
Audio Loudness Normalization using pydub

Normalizes audio files to a target loudness level to enable
fair A/B comparison without volume bias.
"""

import os
import hashlib
from pathlib import Path

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("pydub not installed - loudness normalization disabled")

# Target loudness in dBFS (decibels relative to full scale)
# -14 dBFS is common for streaming services
TARGET_DBFS = -14.0

# Cache directory for normalized files
NORMALIZED_DIR = os.environ.get('NORMALIZED_DIR', 'normalized')


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
    return os.path.join(NORMALIZED_DIR, f"{original_name}_{path_hash}_norm.wav")


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
    Normalize audio file to target loudness.
    
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
        # Load audio
        audio = AudioSegment.from_file(input_path)
        
        # Calculate current loudness
        current_dbfs = audio.dBFS
        
        # Calculate gain needed
        gain_db = target_dbfs - current_dbfs
        
        # Apply gain (with headroom protection)
        # Limit gain to prevent clipping
        if gain_db > 0:
            # When boosting, also normalize to prevent clipping
            audio = normalize(audio, headroom=abs(target_dbfs))
        else:
            # When reducing, just apply gain
            audio = audio + gain_db
        
        # Export normalized file
        audio.export(output_path, format="wav")
        
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
    Pre-normalize all WAV files in a directory.
    Useful for batch processing during scan.
    
    Returns dict mapping original paths to normalized paths.
    """
    if not PYDUB_AVAILABLE:
        return {}
    
    ensure_normalized_dir()
    results = {}
    
    for filename in os.listdir(directory):
        if filename.lower().endswith('.wav'):
            original_path = os.path.abspath(os.path.join(directory, filename))
            
            if not is_normalized(original_path):
                print(f"Normalizing: {filename}")
                normalized_path = normalize_audio(original_path)
            else:
                normalized_path = get_normalized_path(original_path)
            
            results[original_path] = normalized_path
    
    return results
