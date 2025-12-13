# Song Voter

A minimal, blind song voting tool for comparing different versions of audio tracks. Perfect for A/B testing mixes, masters, or production decisions without bias.

## Features

### Voting
- **Blind voting** - Song versions are shuffled for each voter to eliminate order bias
- **Loudness normalization** - All tracks normalized to -14 dBFS for fair comparison
- **Two voting modes** - Thumbs up/down and 1-10 rating scale
- **Minimum listen time** - Configurable requirement before voting is allowed
- **Skip control** - Optional ability to disable skipping songs

### Vote Blocks
- **Create shareable vote sessions** - Generate unique links for specific song subsets
- **Password protection** - Optionally protect vote blocks with passwords
- **Expiration dates** - Set blocks to expire at a specific date/time
- **Per-block settings** - Override global min listen time and skip settings per block
- **Voting restrictions** - Limit by IP address, browser session, or allow unlimited

### Results & Analytics
- **Live results** - View average ratings, thumbs percentages, and vote counts
- **Agreement scores** - See how consistently voters agree on each song
- **Controversial indicators** - Highlight songs with high voter disagreement
- **Rank badges** - Visual indicators for top 3 songs and best version per track
- **Results visibility** - Control when results are shown (public, hidden, or after voting ends)

### UI/UX
- **Real-time audio visualizer** - Multiple modes (bars, oscilloscope, or both)
- **Waveform display** - See song progress with preloaded waveform
- **Chromecast support** - Cast audio via browser Remote Playback API
- **Dark mode UI** - Elite dark aesthetic with monospace typography
- **Mobile responsive** - Optimized for desktop and mobile browsers
- **Draft auto-save** - Votes saved locally in case of connection issues

### Admin Features
- **Song management** - Upload, scan, and delete songs
- **Multi-admin support** - Add additional admin accounts
- **Branding** - Customize title, description, favicon, OG image, and accent color
- **Site password** - Optional global password protection
- **Homepage toggle** - Close voting while keeping vote blocks active

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

3. (Optional) Set admin credentials via environment variables:
   ```yaml
   environment:
     - ADMIN_USER=admin
     - ADMIN_PASS=your-secure-password
   ```

4. Run:
   ```bash
   docker-compose up -d --build
   ```

5. Open http://localhost:5000

## Admin Setup

**Option 1: Environment Variables**  
Set `ADMIN_USER` and `ADMIN_PASS` before first run. The admin account will be created automatically.

**Option 2: Web Setup**  
If no admin exists, visit `/admin/setup` to create your first admin account through the web interface.

**Accessing Admin Panel**  
Once set up, access the admin panel at `/admin/` and log in with your credentials.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# For loudness normalization, install ffmpeg
# macOS: brew install ffmpeg
# Ubuntu: apt install ffmpeg
# Windows: https://ffmpeg.org/download.html

# Set admin credentials
export ADMIN_USER=admin
export ADMIN_PASS=yourpassword

# Run
python app.py
```

After modifying `static/style.css` or `static/app.js`, update cache-busting hashes:

```bash
python update_static_hashes.py
```

## Testing

![Tests](https://github.com/davidtorcivia/song-voter/actions/workflows/tests.yml/badge.svg)

### Backend Tests (pytest)

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest -v

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_voting.py -v
```

### Frontend Tests (Playwright)

```bash
# Install dependencies
npm install

# Install browsers
npx playwright install

# Run all E2E tests
npm test

# Run with UI mode
npm run test:ui

# Run in headed mode (see browser)
npm run test:headed
```

### CI/CD

Tests run automatically on every push and pull request via GitHub Actions. Check the status badge above or visit the Actions tab.

## File Naming Convention

Songs are grouped by base name for comparison. Use this format:
```
SongName - Version A.wav
SongName - Version B.wav
SongName - Mix 1.wav
SongName - Mix 2.wav
SongName - Example.wav
SongName - Example (1).wav
```

The part before ` - ` becomes the base name for grouping.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SONGS_DIR` | `songs/` | Path to audio files (WAV, MP3, FLAC, etc.) |
| `DATABASE_PATH` | `data/song_voter.db` | SQLite database path |
| `NORMALIZED_DIR` | `normalized/` | Cached normalized audio |
| `UPLOADS_DIR` | `uploads/` | Uploaded songs and assets |
| `ADMIN_USER` | - | Initial admin username (optional, can use web setup) |
| `ADMIN_PASS` | - | Initial admin password (optional, can use web setup) |

## API Endpoints

### Public
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main voting page |
| `/results` | GET | Results page |
| `/vote/block/<slug>` | GET | Vote block page |
| `/api/songs` | GET | List all songs |
| `/api/songs/<id>/audio` | GET | Stream audio (normalized) |
| `/api/songs/<id>/vote` | POST | Submit vote |
| `/api/results` | GET | Get voting results |
| `/api/config` | GET | Get frontend config |

### Admin (requires authentication)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/` | GET | Admin dashboard |
| `/admin/blocks` | GET | Vote blocks management |
| `/admin/settings` | POST | Update settings |
| `/admin/blocks` | POST | Create vote block |
| `/admin/blocks/<id>` | PUT | Update vote block |
| `/admin/blocks/<id>` | DELETE | Delete vote block |
| `/api/scan` | POST | Scan songs directory |
| `/api/clear` | POST | Clear all voting data |

## Vote Block Settings

When creating a vote block, you can configure:

- **Name** - Display name for the block
- **Songs** - Select which songs to include
- **Password** - Optional access password
- **Expiration** - Optional expiry date/time
- **Voting Restriction** - `none`, `ip`, or `browser` (session-based)
- **Disable Skip** - Override global setting (Yes/No/Use global)
- **Min Listen Time** - Override global setting (empty = use global)

## License

MIT License - see [LICENSE](LICENSE)
