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

        this.audio = new Audio();
        this.isPlaying = false;

        this.initElements();
        this.initEventListeners();
        this.initAudioListeners();
    }

    initElements() {
        // Setup
        this.scanBtn = document.getElementById('scanBtn');
        this.modeSelect = document.getElementById('modeSelect');
        this.startBtn = document.getElementById('startBtn');
        this.setupSection = document.getElementById('setupSection');

        // Player
        this.playerSection = document.getElementById('playerSection');
        this.songName = document.getElementById('songName');
        this.playBtn = document.getElementById('playBtn');
        this.skipBtn = document.getElementById('skipBtn');
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
        this.scanBtn.addEventListener('click', () => this.scanSongs());
        this.startBtn.addEventListener('click', () => this.startVoting());
        this.playBtn.addEventListener('click', () => this.togglePlay());
        this.skipBtn.addEventListener('click', () => this.skipSong());
        this.progressBar.addEventListener('click', (e) => this.seek(e));
        this.volumeSlider.addEventListener('input', () => this.setVolume());
        this.thumbUpBtn.addEventListener('click', () => this.setThumb(true));
        this.thumbDownBtn.addEventListener('click', () => this.setThumb(false));
        this.ratingSlider.addEventListener('input', () => this.updateRating());
        this.submitBtn.addEventListener('click', () => this.submitVote());
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

    async scanSongs() {
        this.scanBtn.disabled = true;
        this.scanBtn.textContent = 'Scanning...';

        try {
            const response = await fetch('/api/scan', { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                this.songs = data.songs;
                this.baseNames = data.base_names;
                this.populateModeSelect();
                this.showFeedback(`Found ${data.count} songs!`);
                this.startBtn.disabled = false;
            } else {
                this.showFeedback(data.error || 'Scan failed', true);
            }
        } catch (err) {
            this.showFeedback('Error scanning songs', true);
            console.error(err);
        }

        this.scanBtn.disabled = false;
        this.scanBtn.textContent = 'Scan Songs';
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
        this.audio.src = `/api/songs/${song.id}/audio`;
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
        // Auto-advance if already voted, otherwise wait
        // For now, always advance
        // this.playNext();
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
                this.showFeedback('Vote recorded!');
                this.playNext();
            } else {
                this.showFeedback(data.error || 'Vote failed', true);
            }
        } catch (err) {
            this.showFeedback('Error submitting vote', true);
            console.error(err);
        }

        this.submitBtn.disabled = false;
    }

    showFeedback(message, isError = false) {
        this.feedback.textContent = message;
        this.feedback.style.background = isError ? '#e94560' : '#4ecca3';
        this.feedback.classList.add('show');

        setTimeout(() => {
            this.feedback.classList.remove('show');
        }, 2000);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.songVoter = new SongVoter();
});
