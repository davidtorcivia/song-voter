// Song Voter - Main Application Logic

class SongVoter {
    constructor() {
        this.songs = [];
        this.baseNames = [];
        this.queue = [];
        this.currentIndex = -1;
        this.currentSong = null;
        this.mode = 'all';
        this.thumbsValue = null;
        this.ratingValue = 5;

        this.audio = document.getElementById('audioPlayer') || new Audio();
        this.isPlaying = false;

        // Audio context for visualizer
        this.audioContext = null;
        this.analyser = null;

        // Listening time tracking for 20-second requirement
        this.listenedTime = 0;
        this.minListenTime = 20; // seconds
        this.listenInterval = null; // Wall-clock timer

        this.initElements();
        this.initEventListeners();
        this.initAudioListeners();
        this.initCasting();
        this.initVisualizer();
        this.initKeyboardControls();

        // Auto-load songs on startup
        this.autoLoadSongs();
    }

    initElements() {
        // Setup
        this.pageTitle = document.getElementById('pageTitle');
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
        this.playhead = document.getElementById('playhead');
        this.currentTime = document.getElementById('currentTime');
        this.totalTime = document.getElementById('totalTime');
        this.volumeSlider = document.getElementById('volumeSlider');
        this.visualizer = document.getElementById('visualizer');

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

        // Handle browser back button
        window.addEventListener('popstate', (e) => this.handleBackButton(e));

        // Playhead dragging
        this.initSeekDrag();
    }

    initSeekDrag() {
        let isDragging = false;

        const startDrag = (e) => {
            isDragging = true;
            this.seekFromEvent(e);
        };

        const doDrag = (e) => {
            if (!isDragging) return;
            e.preventDefault();
            this.seekFromEvent(e);
        };

        const endDrag = () => {
            isDragging = false;
        };

        // Mouse events
        this.progressBar.addEventListener('mousedown', startDrag);
        document.addEventListener('mousemove', doDrag);
        document.addEventListener('mouseup', endDrag);

        // Touch events
        this.progressBar.addEventListener('touchstart', (e) => {
            isDragging = true;
            this.seekFromEvent(e.touches[0]);
        }, { passive: true });
        document.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            this.seekFromEvent(e.touches[0]);
        }, { passive: true });
        document.addEventListener('touchend', endDrag);
    }

    seekFromEvent(e) {
        const rect = this.progressBar.getBoundingClientRect();
        const x = e.clientX !== undefined ? e.clientX : e.pageX;
        let percent = (x - rect.left) / rect.width;
        percent = Math.max(0, Math.min(1, percent));
        if (!isNaN(this.audio.duration)) {
            this.audio.currentTime = percent * this.audio.duration;
        }
    }

    initKeyboardControls() {
        document.addEventListener('keydown', (e) => {
            // Spacebar to toggle play/pause (when not in an input field)
            if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                e.preventDefault();
                if (this.currentSong) {
                    this.togglePlay();
                }
            }
        });
    }

    handleBackButton(e) {
        if (this.playerSection.style.display === 'block') {
            // Go back to setup instead of leaving page
            e.preventDefault();
            this.audio.pause();
            this.playerSection.style.display = 'none';
            this.setupSection.style.display = 'block';
            if (this.pageTitle) this.pageTitle.textContent = 'Song Voter';
            // Push state again so next back goes to previous page
            history.pushState({ page: 'setup' }, '', '');
        }
    }

    initAudioListeners() {
        this.audio.addEventListener('timeupdate', () => this.updateProgress());
        this.audio.addEventListener('loadedmetadata', () => this.updateDuration());
        this.audio.addEventListener('ended', () => this.onSongEnd());
        this.audio.addEventListener('play', () => {
            this.isPlaying = true;
            this.playBtn.textContent = '❙❙';
            // Setup audio analyser on first play (requires user interaction)
            if (!this.audioContext) {
                this.setupAudioAnalyser();
            } else if (this.audioContext.state === 'suspended') {
                this.audioContext.resume();
            }
            // Start wall-clock timer for listening time
            this.startListenTimer();
        });
        this.audio.addEventListener('pause', () => {
            this.isPlaying = false;
            this.playBtn.textContent = '▶';
            // Stop wall-clock timer
            this.stopListenTimer();
        });
    }

    initCasting() {
        if (!this.castBtn) return;

        // Check if Remote Playback API is available
        if ('remote' in this.audio) {
            this.audio.remote.watchAvailability((available) => {
                this.castBtn.style.display = available ? 'inline-flex' : 'none';
            }).catch(() => {
                // Fallback: always show cast button
                this.castBtn.style.display = 'inline-flex';
            });
        } else {
            this.castBtn.style.display = 'none';
        }
    }

    promptCast() {
        if ('remote' in this.audio) {
            this.audio.remote.prompt().catch(err => {
                console.log('Cast prompt error:', err);
            });
        }
    }

    // === Visualizer ===

    initVisualizer() {
        if (!this.visualizer) return;

        this.visCtx = this.visualizer.getContext('2d');
        this.resizeVisualizer();
        window.addEventListener('resize', () => this.resizeVisualizer());

        // Draw initial idle state immediately
        this.drawIdleVisualizer();
    }

    drawIdleVisualizer() {
        if (!this.visCtx) return;

        const width = this.visualizer.width / window.devicePixelRatio;
        const height = this.visualizer.height / window.devicePixelRatio;

        this.visCtx.fillStyle = '#111111';
        this.visCtx.fillRect(0, 0, width, height);

        // Draw subtle idle bars
        const barCount = 32;
        const barWidth = width / barCount;

        for (let i = 0; i < barCount; i++) {
            const barHeight = 2 + Math.random() * 4;
            this.visCtx.fillStyle = 'rgb(50, 50, 50)';
            this.visCtx.fillRect(i * barWidth, height - barHeight, barWidth - 1, barHeight);
        }
    }

    resizeVisualizer() {
        if (!this.visualizer) return;
        const rect = this.visualizer.getBoundingClientRect();
        this.visualizer.width = rect.width * window.devicePixelRatio;
        this.visualizer.height = rect.height * window.devicePixelRatio;
        this.visCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }

    setupAudioAnalyser() {
        if (this.audioContext) return;

        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 64;

            const source = this.audioContext.createMediaElementSource(this.audio);
            source.connect(this.analyser);
            this.analyser.connect(this.audioContext.destination);

            this.drawVisualizer();
        } catch (err) {
            console.log('Visualizer setup failed:', err);
        }
    }

    drawVisualizer() {
        if (!this.analyser || !this.visCtx) return;

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            requestAnimationFrame(draw);

            this.analyser.getByteFrequencyData(dataArray);

            const width = this.visualizer.width / window.devicePixelRatio;
            const height = this.visualizer.height / window.devicePixelRatio;

            this.visCtx.fillStyle = '#111111';
            this.visCtx.fillRect(0, 0, width, height);

            const barWidth = width / bufferLength;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const barHeight = (dataArray[i] / 255) * height;

                // Gradient from dim to bright based on amplitude
                const brightness = Math.floor(40 + (dataArray[i] / 255) * 80);
                this.visCtx.fillStyle = `rgb(${brightness}, ${brightness}, ${brightness})`;

                this.visCtx.fillRect(x, height - barHeight, barWidth - 1, barHeight);
                x += barWidth;
            }
        };

        draw();
    }

    // === Auto Load ===

    async autoLoadSongs() {
        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'block';
        }

        try {
            // First try to get existing songs
            const response = await fetch('/api/songs');
            const data = await response.json();

            if (data.songs && data.songs.length > 0) {
                this.songs = data.songs;
                await this.loadBaseNames();
                this.startBtn.disabled = false;
                this.showFeedback(`Found ${this.songs.length} songs`);
            } else {
                // No songs, trigger scan
                await this.scanSongs();
            }
        } catch (err) {
            console.error('Auto-load error:', err);
            // Show scan button as fallback
            if (document.getElementById('scanSection')) {
                document.getElementById('scanSection').style.display = 'block';
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
                this.startBtn.disabled = this.songs.length === 0;
                this.showFeedback(`Found ${data.count} songs!`);
            } else {
                this.showFeedback(data.error || 'Scan failed', true);
            }
        } catch (err) {
            this.showFeedback('Scan error', true);
            console.error(err);
        }

        if (this.scanBtn) {
            this.scanBtn.disabled = false;
            this.scanBtn.textContent = 'Rescan';
        }
    }

    async loadBaseNames() {
        try {
            const response = await fetch('/api/base-names');
            const data = await response.json();
            this.baseNames = data.base_names || [];
            this.populateModeSelect();
        } catch (err) {
            console.error('Failed to load base names:', err);
        }
    }

    populateModeSelect() {
        this.modeSelect.innerHTML = '<option value="all">All Songs (Shuffled)</option>';
        this.baseNames.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            this.modeSelect.appendChild(option);
        });
    }

    async startVoting() {
        this.mode = this.modeSelect.value;

        if (this.mode === 'all') {
            this.queue = [...this.songs];
        } else {
            this.queue = this.songs.filter(s => s.base_name === this.mode);
        }

        // Shuffle
        for (let i = this.queue.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [this.queue[i], this.queue[j]] = [this.queue[j], this.queue[i]];
        }

        this.currentIndex = -1;
        this.setupSection.style.display = 'none';
        this.playerSection.style.display = 'block';

        // Push history state for back button handling
        history.pushState({ page: 'player' }, '', '');

        // Resize visualizer now that player section is visible
        // Use requestAnimationFrame to ensure DOM has reflowed
        requestAnimationFrame(() => {
            this.resizeVisualizer();
        });

        this.playNext();
    }

    playNext() {
        this.currentIndex++;

        if (this.currentIndex >= this.queue.length) {
            this.showFeedback('All songs rated!');
            this.setupSection.style.display = 'block';
            this.playerSection.style.display = 'none';
            if (this.pageTitle) this.pageTitle.textContent = 'Song Voter';
            return;
        }

        this.loadSong(this.queue[this.currentIndex]);
    }

    loadSong(song) {
        this.currentSong = song;
        this.songName.textContent = `${this.currentIndex + 1}/${this.queue.length}`;

        // Update page title to base name (hide version info)
        if (this.pageTitle) {
            this.pageTitle.textContent = song.base_name || 'Voting';
        }

        // Reset voting state
        this.thumbsValue = null;
        this.thumbUpBtn.classList.remove('selected');
        this.thumbDownBtn.classList.remove('selected');
        this.ratingSlider.value = 5;
        this.ratingValue.textContent = '5';

        // Reset listening time tracking
        this.stopListenTimer();
        this.listenedTime = 0;
        this.lastTimeUpdate = 0;
        this.updateSubmitButtonState();

        // Load audio
        this.audio.src = `/api/songs/${song.id}/audio`;
        this.audio.load();
        this.audio.play().catch(err => console.log('Autoplay blocked:', err));
    }

    togglePlay() {
        if (this.isPlaying) {
            this.audio.pause();
        } else {
            if (this.audioContext && this.audioContext.state === 'suspended') {
                this.audioContext.resume();
            }
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

        // Update playhead icon position
        if (this.playhead) {
            this.playhead.style.left = `calc(${percent}% - 5px)`;
        }

        // Update submit button state (timer is handled separately)
        this.updateSubmitButtonState();
    }

    startListenTimer() {
        if (this.listenInterval) return; // Already running
        this.listenInterval = setInterval(() => {
            this.listenedTime += 0.1;
            this.updateSubmitButtonState();
        }, 100);
    }

    stopListenTimer() {
        if (this.listenInterval) {
            clearInterval(this.listenInterval);
            this.listenInterval = null;
        }
    }

    updateSubmitButtonState() {
        if (!this.submitBtn) return;

        const canVote = this.listenedTime >= this.minListenTime;

        // Update submit/vote button
        if (canVote) {
            this.submitBtn.disabled = false;
            this.submitBtn.textContent = 'Next →';
        } else {
            this.submitBtn.disabled = true;
            const remaining = Math.ceil(this.minListenTime - this.listenedTime);
            this.submitBtn.textContent = `Listen ${remaining}s`;
        }

        // Disable/enable voting controls (thumbs and rating) based on listen time
        if (this.thumbUpBtn) this.thumbUpBtn.disabled = !canVote;
        if (this.thumbDownBtn) this.thumbDownBtn.disabled = !canVote;
        if (this.ratingSlider) this.ratingSlider.disabled = !canVote;
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
        // Song finished - just pause and wait for user to vote or skip
        // Don't auto-submit, let user decide
        this.stopListenTimer();
        this.showFeedback('Song ended - vote or skip');
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

        this.submitBtn.disabled = true;
        const rating = parseInt(this.ratingSlider.value);

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
