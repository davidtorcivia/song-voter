// Song Voter - Main Application Logic

class SongVoter {
    constructor() {
        this.songs = [];
        this.baseNames = [];
        this.queue = [];
        this.currentIndex = -1;
        this.currentSong = null;
        this.mode = 'all'; // 'all' or specific base_name
        this.thumbsValue = null;
        this.ratingValue = 5;

        // Use HTML audio element for Airplay support
        this.audio = document.getElementById('audioPlayer') || new Audio();
        this.isPlaying = false;
        this.isCasting = false;

        this.initElements();
        this.initEventListeners();
        this.initAudioListeners();
        this.initCasting();

        // Auto-load songs on startup
        this.autoLoadSongs();
    }

    initElements() {
        // Setup
        this.scanBtn = document.getElementById('scanBtn');
        this.modeSelect = document.getElementById('modeSelect');
        this.startBtn = document.getElementById('startBtn');
        this.setupSection = document.getElementById('setupSection');
        this.loadingIndicator = document.getElementById('loadingIndicator');

        // Player
        this.playerSection = document.getElementById('playerSection');
        this.songName = document.getElementById('songName');
        this.playBtn = document.getElementById('playBtn');
        this.skipBtn = document.getElementById('skipBtn');
        this.castBtn = document.getElementById('castBtn');
        this.progressBar = document.getElementById('progressBar');
        this.progressFill = document.getElementById('progressFill');
        this.currentTime = document.getElementById('currentTime');
        this.totalTime = document.getElementById('totalTime');
        this.volumeSlider = document.getElementById('volumeSlider');

        // Voting
        this.thumbUpBtn = document.getElementById('thumbUpBtn');
        this.thumbDownBtn = document.getElementById('thumbDownBtn');
        this.ratingSlider = document.getElementById('ratingSlider');
        this.ratingValue = document.getElementById('ratingValue');
        this.submitBtn = document.getElementById('submitBtn');

        // Feedback
        this.feedback = document.getElementById('feedback');
    }

    initEventListeners() {
        if (this.scanBtn) {
            this.scanBtn.addEventListener('click', () => this.scanSongs());
        }
        this.startBtn.addEventListener('click', () => this.startVoting());
        this.playBtn.addEventListener('click', () => this.togglePlay());
        this.skipBtn.addEventListener('click', () => this.skipSong());
        this.progressBar.addEventListener('click', (e) => this.seek(e));
        this.volumeSlider.addEventListener('input', () => this.setVolume());
        this.thumbUpBtn.addEventListener('click', () => this.setThumb(true));
        this.thumbDownBtn.addEventListener('click', () => this.setThumb(false));
        this.ratingSlider.addEventListener('input', () => this.updateRating());
        this.submitBtn.addEventListener('click', () => this.submitVote());

        if (this.castBtn) {
            this.castBtn.addEventListener('click', () => this.promptCast());
        }
    }

    initAudioListeners() {
        this.audio.addEventListener('timeupdate', () => this.updateProgress());
        this.audio.addEventListener('loadedmetadata', () => this.updateDuration());
        this.audio.addEventListener('ended', () => this.onSongEnd());
        this.audio.addEventListener('play', () => {
            this.isPlaying = true;
            this.playBtn.textContent = '⏸';
        });
        this.audio.addEventListener('pause', () => {
            this.isPlaying = false;
            this.playBtn.textContent = '▶';
        });
    }

    // Remote Playback API for casting (Chromecast)
    initCasting() {
        // Check if Remote Playback API is supported
        if (!('remote' in HTMLMediaElement.prototype)) {
            console.log('Remote Playback API not supported');
            // Still show button for potential Airplay support via native controls
            return;
        }

        // Watch for device availability
        this.audio.remote.watchAvailability((available) => {
            if (this.castBtn) {
                this.castBtn.style.display = 'flex';
                // Always enabled - let user try even if no devices detected
            }
        }).catch((error) => {
            console.log('Remote playback availability watching failed:', error);
            if (this.castBtn) {
                // Still show the button - let user try
                this.castBtn.style.display = 'flex';
            }
        });

        // Listen for connection state changes
        this.audio.remote.addEventListener('connecting', () => {
            this.showFeedback('Connecting...');
            if (this.castBtn) this.castBtn.classList.add('connecting');
        });

        this.audio.remote.addEventListener('connect', () => {
            this.isCasting = true;
            this.showFeedback('Connected');
            if (this.castBtn) {
                this.castBtn.classList.remove('connecting');
                this.castBtn.classList.add('casting');
            }
        });

        this.audio.remote.addEventListener('disconnect', () => {
            this.isCasting = false;
            this.showFeedback('Disconnected');
            if (this.castBtn) {
                this.castBtn.classList.remove('connecting', 'casting');
            }
        });
    }

    // Always show device picker (allows switching devices)
    async promptCast() {
        if (!this.audio.remote) {
            this.showFeedback('Casting not supported', true);
            return;
        }

        try {
            // Always prompt - this allows switching to a different device
            await this.audio.remote.prompt();
        } catch (error) {
            if (error.name === 'NotSupportedError') {
                this.showFeedback('No cast devices found', true);
            } else if (error.name === 'NotAllowedError') {
                // User cancelled the prompt - that's fine
                console.log('User cancelled cast prompt');
            } else if (error.name === 'InvalidStateError') {
                // Already connected - prompt again to switch
                try {
                    await this.audio.remote.prompt();
                } catch (e) {
                    console.log('Could not switch devices:', e);
                }
            } else {
                console.error('Cast error:', error);
                this.showFeedback('Cast failed', true);
            }
        }
    }

    // Auto-load songs when page loads
    async autoLoadSongs() {
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'block';
        }
        if (this.scanBtn) {
            this.scanBtn.style.display = 'none';
        }

        try {
            // First try to get existing songs from API
            const response = await fetch('/api/songs');
            const data = await response.json();

            if (data.songs && data.songs.length > 0) {
                this.songs = data.songs;
                // Get base names
                const baseNamesResponse = await fetch('/api/base-names');
                const baseNamesData = await baseNamesResponse.json();
                this.baseNames = baseNamesData.base_names || [];
                this.populateModeSelect();
                this.startBtn.disabled = false;
            } else {
                // No songs in DB, do a scan
                await this.scanSongs();
            }
        } catch (err) {
            console.error('Auto-load failed:', err);
            // Fall back to showing scan button
            if (this.scanBtn) {
                this.scanBtn.style.display = 'block';
            }
        }

        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'none';
        }
    }

    async scanSongs() {
        if (this.scanBtn) {
            this.scanBtn.disabled = true;
            this.scanBtn.textContent = 'Scanning...';
        }

        try {
            const response = await fetch('/api/scan', { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.songs = data.songs;
                this.baseNames = data.base_names;
                this.populateModeSelect();
                if (data.count > 0) {
                    this.showFeedback(`Found ${data.count} songs`);
                    this.startBtn.disabled = false;
                } else {
                    this.showFeedback('No songs found', true);
                }
            } else {
                this.showFeedback(data.error || 'Scan failed', true);
            }
        } catch (err) {
            this.showFeedback('Error scanning songs', true);
            console.error(err);
        }

        if (this.scanBtn) {
            this.scanBtn.disabled = false;
            this.scanBtn.textContent = 'Rescan';
        }
    }

    populateModeSelect() {
        this.modeSelect.innerHTML = '<option value="all">All Songs (Shuffled)</option>';

        for (const name of this.baseNames) {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            this.modeSelect.appendChild(option);
        }
    }

    startVoting() {
        this.mode = this.modeSelect.value;
        this.buildQueue();

        if (this.queue.length === 0) {
            this.showFeedback('No songs to play!', true);
            return;
        }

        this.setupSection.style.display = 'none';
        this.playerSection.classList.add('visible');
        this.currentIndex = -1;
        this.playNext();
    }

    buildQueue() {
        let songsToQueue;

        if (this.mode === 'all') {
            songsToQueue = [...this.songs];
        } else {
            songsToQueue = this.songs.filter(s => s.base_name === this.mode);
        }

        // Shuffle
        this.queue = this.shuffle(songsToQueue);
    }

    shuffle(array) {
        const shuffled = [...array];
        for (let i = shuffled.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        return shuffled;
    }

    playNext() {
        this.currentIndex++;

        if (this.currentIndex >= this.queue.length) {
            // Reshuffle and start over
            this.queue = this.shuffle(this.queue);
            this.currentIndex = 0;
        }

        this.currentSong = this.queue[this.currentIndex];
        this.loadSong(this.currentSong);
        this.resetVoting();
    }

    loadSong(song) {
        this.songName.textContent = song.base_name;
        // Use absolute URL for casting compatibility
        const audioUrl = new URL(`/api/songs/${song.id}/audio`, window.location.origin).href;
        this.audio.src = audioUrl;
        this.audio.load();
        this.audio.play();
    }

    resetVoting() {
        this.thumbsValue = null;
        this.thumbUpBtn.classList.remove('selected');
        this.thumbDownBtn.classList.remove('selected');
        this.ratingSlider.value = 5;
        this.ratingValue.textContent = '5';
    }

    togglePlay() {
        if (this.isPlaying) {
            this.audio.pause();
        } else {
            this.audio.play();
        }
    }

    skipSong() {
        this.playNext();
    }

    seek(e) {
        const rect = this.progressBar.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        this.audio.currentTime = percent * this.audio.duration;
    }

    setVolume() {
        this.audio.volume = this.volumeSlider.value / 100;
    }

    updateProgress() {
        const percent = (this.audio.currentTime / this.audio.duration) * 100;
        this.progressFill.style.width = `${percent}%`;
        this.currentTime.textContent = this.formatTime(this.audio.currentTime);
    }

    updateDuration() {
        this.totalTime.textContent = this.formatTime(this.audio.duration);
    }

    formatTime(seconds) {
        if (isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    onSongEnd() {
        // Song ended - wait for user to vote or skip
    }

    setThumb(isUp) {
        this.thumbsValue = isUp;
        this.thumbUpBtn.classList.toggle('selected', isUp);
        this.thumbDownBtn.classList.toggle('selected', !isUp);
    }

    updateRating() {
        this.ratingValue.textContent = this.ratingSlider.value;
    }

    async submitVote() {
        if (!this.currentSong) return;

        const rating = parseInt(this.ratingSlider.value);

        this.submitBtn.disabled = true;

        try {
            const response = await fetch(`/api/songs/${this.currentSong.id}/vote`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    thumbs_up: this.thumbsValue,
                    rating: rating
                })
            });

            const data = await response.json();

            if (data.success) {
                this.showFeedback('Saved');
                this.playNext();
            } else {
                this.showFeedback(data.error || 'Vote failed', true);
            }
        } catch (err) {
            this.showFeedback('Error', true);
            console.error(err);
        }

        this.submitBtn.disabled = false;
    }

    showFeedback(message, isError = false) {
        this.feedback.textContent = message;
        this.feedback.style.background = isError ? 'var(--danger)' : 'var(--bg-card)';
        this.feedback.classList.add('show');

        setTimeout(() => {
            this.feedback.classList.remove('show');
        }, 1500);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.songVoter = new SongVoter();
});
