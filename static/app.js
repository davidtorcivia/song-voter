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

        // HEOS state
        this.heosDevices = [];
        this.heosPlaying = false;
        this.selectedHeos = null;

        // AirPlay state
        this.airplayDevices = [];
        this.airplayPlaying = false;
        this.selectedAirplay = null;

        this.initElements();
        this.initEventListeners();
        this.initAudioListeners();
        this.initCasting();
        this.initHeos();
        this.initAirplay();

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

        // HEOS
        this.heosSelect = document.getElementById('heosSelect');
        this.heosPlayBtn = document.getElementById('heosPlayBtn');

        // AirPlay
        this.airplaySelect = document.getElementById('airplaySelect');
        this.airplayPlayBtn = document.getElementById('airplayPlayBtn');
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

        // HEOS listeners
        if (this.heosSelect) {
            this.heosSelect.addEventListener('change', () => this.onHeosSelect());
            this.heosSelect.addEventListener('focus', () => this.discoverHeos());
        }
        if (this.heosPlayBtn) {
            this.heosPlayBtn.addEventListener('click', () => this.toggleHeosPlay());
        }

        // AirPlay listeners
        if (this.airplaySelect) {
            this.airplaySelect.addEventListener('change', () => this.onAirplaySelect());
            this.airplaySelect.addEventListener('focus', () => this.discoverAirplay());
        }
        if (this.airplayPlayBtn) {
            this.airplayPlayBtn.addEventListener('click', () => this.toggleAirplayPlay());
        }
    }

    initAudioListeners() {
        this.audio.addEventListener('timeupdate', () => this.updateProgress());
        this.audio.addEventListener('loadedmetadata', () => this.updateDuration());
        this.audio.addEventListener('ended', () => this.onSongEnd());
        this.audio.addEventListener('play', () => {
            this.isPlaying = true;
            this.playBtn.textContent = '❙❙';
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

    // ============ HEOS Methods ============

    initHeos() {
        // Try to load cached devices on init
        this.loadCachedHeosDevices();
    }

    async loadCachedHeosDevices() {
        try {
            const response = await fetch('/api/heos/devices');
            const data = await response.json();
            if (data.devices && data.devices.length > 0) {
                this.heosDevices = data.devices;
                this.populateHeosSelect();
            }
        } catch (err) {
            console.log('No cached HEOS devices');
        }
    }

    async discoverHeos() {
        if (!this.heosSelect) return;

        // Only discover if we don't have devices yet
        if (this.heosDevices.length > 0) return;

        this.heosSelect.innerHTML = '<option value="">Scanning...</option>';

        try {
            const response = await fetch('/api/heos/discover', { method: 'POST' });
            const data = await response.json();

            this.heosDevices = data.devices || [];
            this.populateHeosSelect();

            if (this.heosDevices.length === 0) {
                this.showFeedback('No HEOS devices found', true);
            } else {
                this.showFeedback(`Found ${this.heosDevices.length} HEOS device(s)`);
            }
        } catch (err) {
            console.error('HEOS discovery error:', err);
            this.heosSelect.innerHTML = '<option value="">Discovery failed</option>';
        }
    }

    populateHeosSelect() {
        if (!this.heosSelect) return;

        this.heosSelect.innerHTML = '<option value="">Select HEOS device...</option>';

        for (const device of this.heosDevices) {
            const option = document.createElement('option');
            option.value = JSON.stringify({ host: device.host, pid: device.pid });
            option.textContent = device.name + (device.model ? ` (${device.model})` : '');
            this.heosSelect.appendChild(option);
        }

        // Add rescan option
        const rescanOption = document.createElement('option');
        rescanOption.value = 'rescan';
        rescanOption.textContent = '↻ Rescan for devices...';
        this.heosSelect.appendChild(rescanOption);
    }

    onHeosSelect() {
        if (!this.heosSelect || !this.heosPlayBtn) return;

        const value = this.heosSelect.value;

        if (value === 'rescan') {
            this.heosDevices = [];
            this.discoverHeos();
            return;
        }

        if (value) {
            this.selectedHeos = JSON.parse(value);
            this.heosPlayBtn.disabled = false;
        } else {
            this.selectedHeos = null;
            this.heosPlayBtn.disabled = true;
        }
    }

    async toggleHeosPlay() {
        if (!this.selectedHeos || !this.currentSong) return;

        if (this.heosPlaying) {
            // Stop HEOS playback
            await this.stopHeosPlay();
        } else {
            // Start HEOS playback
            await this.startHeosPlay();
        }
    }

    async startHeosPlay() {
        if (!this.selectedHeos || !this.currentSong) return;

        this.heosPlayBtn.disabled = true;
        this.heosPlayBtn.textContent = '...';

        try {
            const response = await fetch('/api/heos/play', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    host: this.selectedHeos.host,
                    pid: this.selectedHeos.pid,
                    song_id: this.currentSong.id
                })
            });

            const data = await response.json();

            if (data.success) {
                this.heosPlaying = true;
                this.heosPlayBtn.textContent = '■';
                this.heosPlayBtn.classList.add('playing');
                this.showFeedback('Playing on HEOS');

                // Pause local playback
                this.audio.pause();
            } else {
                this.showFeedback(data.error || 'HEOS play failed', true);
                this.heosPlayBtn.textContent = '▸';
            }
        } catch (err) {
            console.error('HEOS play error:', err);
            this.showFeedback('HEOS error', true);
            this.heosPlayBtn.textContent = '▸';
        }

        this.heosPlayBtn.disabled = false;
    }

    async stopHeosPlay() {
        if (!this.selectedHeos) return;

        try {
            await fetch('/api/heos/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    host: this.selectedHeos.host,
                    pid: this.selectedHeos.pid
                })
            });
        } catch (err) {
            console.error('HEOS stop error:', err);
        }

        this.heosPlaying = false;
        this.heosPlayBtn.textContent = '▸';
        this.heosPlayBtn.classList.remove('playing');
    }

    // ============ AirPlay Methods ============

    initAirplay() {
        // Try to load cached devices on init
        this.loadCachedAirplayDevices();
    }

    async loadCachedAirplayDevices() {
        try {
            const response = await fetch('/api/airplay/devices');
            const data = await response.json();
            if (data.devices && data.devices.length > 0) {
                this.airplayDevices = data.devices;
                this.populateAirplaySelect();
            }
        } catch (err) {
            console.log('No cached AirPlay devices');
        }
    }

    async discoverAirplay() {
        if (!this.airplaySelect) return;

        // Only discover if we don't have devices yet
        if (this.airplayDevices.length > 0) return;

        this.airplaySelect.innerHTML = '<option value="">Scanning...</option>';

        try {
            const response = await fetch('/api/airplay/discover', { method: 'POST' });
            const data = await response.json();

            if (data.error) {
                this.airplaySelect.innerHTML = '<option value="">pyatv not installed</option>';
                return;
            }

            this.airplayDevices = data.devices || [];
            this.populateAirplaySelect();

            if (this.airplayDevices.length === 0) {
                this.showFeedback('No AirPlay devices found', true);
            } else {
                this.showFeedback(`Found ${this.airplayDevices.length} AirPlay device(s)`);
            }
        } catch (err) {
            console.error('AirPlay discovery error:', err);
            this.airplaySelect.innerHTML = '<option value="">Discovery failed</option>';
        }
    }

    populateAirplaySelect() {
        if (!this.airplaySelect) return;

        this.airplaySelect.innerHTML = '<option value="">Select AirPlay device...</option>';

        for (const device of this.airplayDevices) {
            const option = document.createElement('option');
            option.value = JSON.stringify({ address: device.address });
            option.textContent = device.name + (device.model ? ` (${device.model})` : '');
            this.airplaySelect.appendChild(option);
        }

        // Add rescan option
        const rescanOption = document.createElement('option');
        rescanOption.value = 'rescan';
        rescanOption.textContent = '↻ Rescan...';
        this.airplaySelect.appendChild(rescanOption);
    }

    onAirplaySelect() {
        if (!this.airplaySelect || !this.airplayPlayBtn) return;

        const value = this.airplaySelect.value;

        if (value === 'rescan') {
            this.airplayDevices = [];
            this.discoverAirplay();
            return;
        }

        if (value) {
            this.selectedAirplay = JSON.parse(value);
            this.airplayPlayBtn.disabled = false;
        } else {
            this.selectedAirplay = null;
            this.airplayPlayBtn.disabled = true;
        }
    }

    async toggleAirplayPlay() {
        if (!this.selectedAirplay || !this.currentSong) return;

        if (this.airplayPlaying) {
            await this.stopAirplayPlay();
        } else {
            await this.startAirplayPlay();
        }
    }

    async startAirplayPlay() {
        if (!this.selectedAirplay || !this.currentSong) return;

        this.airplayPlayBtn.disabled = true;
        this.airplayPlayBtn.textContent = '...';

        try {
            const response = await fetch('/api/airplay/play', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: this.selectedAirplay.address,
                    song_id: this.currentSong.id
                })
            });

            const data = await response.json();

            if (data.success) {
                this.airplayPlaying = true;
                this.airplayPlayBtn.textContent = '■';
                this.airplayPlayBtn.classList.add('playing');
                this.showFeedback('Playing on AirPlay');

                // Pause local playback
                this.audio.pause();
            } else {
                this.showFeedback(data.error || 'AirPlay failed', true);
                this.airplayPlayBtn.textContent = '▸';
            }
        } catch (err) {
            console.error('AirPlay error:', err);
            this.showFeedback('AirPlay error', true);
            this.airplayPlayBtn.textContent = '▸';
        }

        this.airplayPlayBtn.disabled = false;
    }

    async stopAirplayPlay() {
        if (!this.selectedAirplay) return;

        try {
            await fetch('/api/airplay/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: this.selectedAirplay.address
                })
            });
        } catch (err) {
            console.error('AirPlay stop error:', err);
        }

        this.airplayPlaying = false;
        this.airplayPlayBtn.textContent = '▸';
        this.airplayPlayBtn.classList.remove('playing');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.songVoter = new SongVoter();
});
