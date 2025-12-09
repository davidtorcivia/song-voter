# Song Voter

A minimal, blind song voting tool for comparing different versions of audio tracks. Perfect for A/B testing mixes, masters, or production decisions without bias.

## Features

- **Blind voting** - Song versions are shuffled and anonymized during voting
- **Loudness normalization** - All tracks normalized to -14 dBFS for fair comparison
- **Two voting modes** - Thumbs up/down and 1-10 rating scale
- **Audio visualizer** - Real-time frequency visualization
- **Chromecast support** - Cast to compatible devices via browser
- **Results aggregation** - View average ratings and thumbs percentages
- **Dark mode UI** - Minimal, elite aesthetic with monospace typography
- **Mobile responsive** - Works on desktop and mobile browsers

## Quick Start (Docker)

1. Clone the repository:
   ```bash
   git clone https://github.com/davidtorcivia/song-voter.git
   cd song-voter
   ```

2. Edit `docker-compose.yml` and set your songs folder path:
   ```yaml
   volumes:
     - /path/to/your/songs:/app/songs:ro
   ```

3. Run:
   ```bash
   docker-compose up -d --build
   ```

4. Open http://localhost:5000

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# For loudness normalization, install ffmpeg
# macOS: brew install ffmpeg
# Ubuntu: apt install ffmpeg
# Windows: https://ffmpeg.org/download.html

# Run
python app.py
```

## File Naming Convention

Songs are grouped by base name for comparison. Use this format:
```
SongName - Version A.wav
SongName - Version B.wav
SongName - Mix 1.wav
SongName - Mix 2.wav
```

The part before ` - ` becomes the base name for grouping.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main voting page |
| `/results` | GET | Results page |
| `/api/songs` | GET | List all songs |
| `/api/songs/<id>/audio` | GET | Stream audio (normalized) |
| `/api/songs/<id>/vote` | POST | Submit vote |
| `/api/scan` | POST | Scan songs directory |
| `/api/results` | GET | Get voting results |
| `/api/clear` | POST | Clear all data |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SONGS_DIR` | `songs/` | Path to WAV files |
| `DATABASE_PATH` | `data/song_voter.db` | SQLite database path |
| `NORMALIZED_DIR` | `normalized/` | Cached normalized audio |

## License

MIT License - see [LICENSE](LICENSE)
