"""
Audio Waveform Generation

Generates compact JSON waveform data (peaks) for audio visualization.
Uses pydub to analyze audio files and extract RMS amplitude data.
"""

import os
import json
import math
from pathlib import Path

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("pydub not installed - waveform generation disabled")

# Directory to store cached waveform JSON files
WAVEFORM_DIR = os.environ.get('WAVEFORM_DIR', os.path.join('data', 'waveforms'))

def ensure_waveform_dir():
    """Create waveform directory if it doesn't exist."""
    os.makedirs(WAVEFORM_DIR, exist_ok=True)

def get_waveform_path(song_id):
    """Get the path to the cached waveform JSON file for a song ID."""
    return os.path.join(WAVEFORM_DIR, f"{song_id}.json")

def generate_waveform(input_path, song_id, num_bars=200):
    """
    Generate waveform data for an audio file and cache it.
    
    Args:
        input_path: Path to the audio file
        song_id: Unique ID of the song (used for filename)
        num_bars: Number of data points to extract (default 200)
        
    Returns:
        List of float values (0.0 - 1.0) representing peaks, or None if failed
    """
    if not PYDUB_AVAILABLE:
        return None
        
    ensure_waveform_dir()
    output_path = get_waveform_path(song_id)
    
    # Return cached if exists
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r') as f:
                return json.load(f)
        except:
            pass # Re-generate if corrupt

    try:
        print(f"Generating waveform for: {Path(input_path).name}")
        audio = AudioSegment.from_file(input_path)
        
        # If stereo, mix to mono for analysis
        if audio.channels > 1:
            audio = audio.set_channels(1)
            
        data = audio.get_array_of_samples()
        
        # Calculate chunk size to get exactly num_bars
        chunk_size = math.ceil(len(data) / num_bars)
        peaks = []
        
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            if not chunk:
                continue
                
            # Calculate RMS (Root Mean Square) for this chunk
            # This is better than max peak for representing perceived loudness
            sum_squares = sum(float(s)**2 for s in chunk)
            rms = math.sqrt(sum_squares / len(chunk))
            peaks.append(rms)
            
        # Normalize peaks to 0.0 - 1.0 range
        if peaks:
            max_peak = max(peaks)
            if max_peak > 0:
                peaks = [p / max_peak for p in peaks]
        else:
            peaks = [0.0] * num_bars
            
        # Ensure we have exactly num_bars (padding/truncating if needed due to rounding)
        if len(peaks) > num_bars:
            peaks = peaks[:num_bars]
        while len(peaks) < num_bars:
            peaks.append(0.0)
            
        # Cache to disk
        with open(output_path, 'w') as f:
            json.dump(peaks, f)
            
        return peaks
        
    except Exception as e:
        print(f"Waveform generation failed for {input_path}: {e}")
        return None

def delete_waveform(song_id):
    """Delete cached waveform for a song."""
    path = get_waveform_path(song_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            print(f"Failed to delete waveform {path}: {e}")

def get_or_generate_waveform(input_path, song_id):
    """Get waveform data, generating it if necessary."""
    ensure_waveform_dir()
    output_path = get_waveform_path(song_id)
    
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r') as f:
                return json.load(f)
        except:
            pass
            
    return generate_waveform(input_path, song_id)
