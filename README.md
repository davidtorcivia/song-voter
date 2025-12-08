# Song Voter

A minimal, blind song voting tool for comparing different versions of songs.

## Features

- **Blind Voting**: Shows only the base song name (e.g., "The Runoff"), hiding version numbers
- **Audio Controls**: Play/pause, volume, progress bar with scrubbing, skip
- **Voting**: Thumbs up/down + 1-10 rating (aggregated averages)
- **Modes**: All songs shuffled, or single song group
- **Results Page**: View aggregate stats (revealed filenames, avg rating, thumbs %)

## Quick Start (Docker)

1. Edit `docker-compose.yml` and update the songs path:
   ```yaml
   volumes:
     - /path/to/your/songs:/app/songs:ro
   ```

2. Start the container:
   ```bash
   docker-compose up -d
   ```

3. Open `http://localhost:5000` in your browser

4. Click "Scan Songs Folder" to load your WAV files

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Create a songs folder with WAV files
mkdir songs
# ... add your WAV files ...

# Run the app
python app.py
```

Open `http://localhost:5000`

## Usage

1. **Scan Songs**: Click "Scan Songs Folder" to load WAV files from the songs directory
2. **Choose Mode**: Select "All Songs (Shuffled)" or a specific song group
3. **Vote**: Listen, then:
   - Click 👍 or 👎 
   - Set rating 1-10
   - Click "Submit & Next"
4. **View Results**: Click "View Results" to see aggregate stats (reveals full filenames)

## Folder Structure

```
songs/
├── The Runoff.wav
├── The Runoff (1).wav
├── The Runoff (2).wav
├── Another Song.wav
└── Another Song (1).wav
```

Songs are grouped by base name. Version suffixes like `(1)`, `(2)` are hidden during voting.
