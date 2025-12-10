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

        // Listening time tracking for minimum requirement
        this.listenedTime = 0;
        this.minListenTime = 20; // Will be updated from config
        this.listenInterval = null; // Wall-clock timer
        this.disableSkip = false; // Will be updated from config

        this.initElements();
        this.initEventListeners();
        this.initAudioListeners();
        this.initCasting();
        this.initVisualizer();
        this.initKeyboardControls();

        // Load config then auto-load songs
        this.loadConfig().then(() => this.autoLoadSongs());
    }

    async loadConfig() {
        try {
            const res = await fetch('/api/config');
            const config = await res.json();

            this.minListenTime = config.min_listen_time || 20;
            this.disableSkip = config.disable_skip || false;

            // Hide skip button if disabled
            if (this.disableSkip && this.skipBtn) {
                this.skipBtn.style.display = 'none';
            }
        } catch (err) {
            console.error('Failed to load config:', err);
        }
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

        // Waveform elements
        this.waveformCanvas = document.getElementById('waveformCanvas');
        this.waveCtx = this.waveformCanvas ? this.waveformCanvas.getContext('2d') : null;
        this.waveData = null;

        // Feedback
        this.feedback = document.getElementById('feedback');

        // Cache accent color
        this.accentColor = getComputedStyle(document.body).getPropertyValue('--accent-color').trim() || '#ffffff';
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
        if (!this.waveformCanvas) return;

        let isDragging = false;

        const startDrag = (e) => {
            isDragging = true;
            this.seekFromEvent(e);
        };

        const endDrag = () => {
            isDragging = false;
        };

        this.waveformCanvas.addEventListener('mousedown', startDrag);
        document.addEventListener('mousemove', (e) => {
            if (isDragging) this.seekFromEvent(e);
        });
        document.addEventListener('mouseup', endDrag);

        // Hover effect tracking
        this.hoverX = -1;
        this.waveformCanvas.addEventListener('mousemove', (e) => {
            const rect = this.waveformCanvas.getBoundingClientRect();
            this.hoverX = e.clientX - rect.left;
        });
        this.waveformCanvas.addEventListener('mouseleave', () => {
            this.hoverX = -1;
        });

        this.waveformCanvas.addEventListener('touchstart', (e) => {
            startDrag(e.touches[0]);
        }, { passive: true });
        document.addEventListener('touchmove', (e) => {
            if (!isDragging) return;
            this.seekFromEvent(e.touches[0]);
        }, { passive: true });
        document.addEventListener('touchend', endDrag);

        // Start render loop
        this.animateWaveform();
    }

    seekFromEvent(e) {
        if (!this.waveformCanvas) return;
        const rect = this.waveformCanvas.getBoundingClientRect();
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
            } else if (this.audioContext.state !== 'running') {
                this.audioContext.resume().then(() => {
                    console.log('AudioContext resumed successfully');
                }).catch(err => console.log('Resume failed:', err));
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
        const barCount = 48;
        const barWidth = (width / barCount) * 0.8;
        const gap = (width / barCount) * 0.2;

        for (let i = 0; i < barCount; i++) {
            const barHeight = 2 + Math.random() * 4;
            // Monochrome idle
            const light = 20;
            this.visCtx.fillStyle = `hsl(0, 0%, ${light}%)`;
            this.visCtx.fillRect(i * (barWidth + gap), height - barHeight, barWidth, barHeight);
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
        const frequencyData = new Uint8Array(bufferLength);
        const mode = window.VISUALIZER_MODE || 'bars';

        // Trail history for ghost effect
        const trailHistory = [];
        const maxTrails = 5;

        // Get accent color
        const accentColor = this.accentColor || '#a78bfa';

        const draw = () => {
            requestAnimationFrame(draw);

            const width = this.visualizer.width / window.devicePixelRatio;
            const height = this.visualizer.height / window.devicePixelRatio;

            // Clear with dark background
            this.visCtx.fillStyle = '#111111';
            this.visCtx.fillRect(0, 0, width, height);

            // Get appropriate data
            this.analyser.getByteTimeDomainData(dataArray);
            this.analyser.getByteFrequencyData(frequencyData);

            // Parse accent color to get HSL values for dynamic coloring
            const accentHex = accentColor.replace('#', '');
            const r = parseInt(accentHex.substr(0, 2), 16) / 255;
            const g = parseInt(accentHex.substr(2, 2), 16) / 255;
            const b = parseInt(accentHex.substr(4, 2), 16) / 255;
            const max = Math.max(r, g, b), min = Math.min(r, g, b);
            let h = 0;
            if (max !== min) {
                const d = max - min;
                if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
                else if (max === g) h = ((b - r) / d + 2) / 6;
                else h = ((r - g) / d + 4) / 6;
            }
            const accentHue = Math.round(h * 360);

            // Draw bars first if mode is 'bars' or 'both'
            if (mode === 'bars' || mode === 'both') {
                const barCount = 48;
                const barWidth = (width / barCount) * 0.8;
                const gap = (width / barCount) * 0.2;

                for (let i = 0; i < barCount; i++) {
                    const idx = Math.floor(i * bufferLength / barCount);
                    const value = frequencyData[idx] / 255;
                    const barHeight = value * height * 0.85;
                    const x = i * (barWidth + gap);

                    // Use accent hue for bars with varying saturation
                    const hueShift = (i / barCount) * 30 - 15; // -15 to +15 hue shift
                    const sat = 30 + value * 40;
                    const light = 25 + value * 35;
                    const alpha = mode === 'both' ? 0.4 : 0.7;
                    this.visCtx.fillStyle = `hsla(${accentHue + hueShift}, ${sat}%, ${light}%, ${alpha})`;
                    this.visCtx.fillRect(x, height - barHeight, barWidth, barHeight);
                }
            }

            // Draw oscilloscope if mode is 'wave' or 'both'
            if (mode === 'wave' || mode === 'both') {
                // Store current frame points for trails
                const currentPoints = [];
                const sliceWidth = width / bufferLength;

                for (let i = 0; i < bufferLength; i++) {
                    const v = dataArray[i] / 128.0;
                    const y = (v * height) / 2;
                    currentPoints.push({ x: i * sliceWidth, y });
                }

                // Add to trail history
                trailHistory.unshift(currentPoints);
                if (trailHistory.length > maxTrails) trailHistory.pop();

                // Draw trails (oldest to newest, fading) using accent color
                for (let t = trailHistory.length - 1; t >= 0; t--) {
                    const points = trailHistory[t];
                    const trailAlpha = (1 - t / maxTrails) * 0.4;

                    if (t > 0) {
                        this.visCtx.strokeStyle = `hsla(${accentHue}, 70%, 60%, ${trailAlpha})`;
                        this.visCtx.lineWidth = 1;
                        this.visCtx.beginPath();
                        this.drawSmoothCurve(points, false);
                        this.visCtx.stroke();
                    }
                }

                // Create KILLER gradient - accent to bright white to complementary to accent
                const gradient = this.visCtx.createLinearGradient(0, 0, width, 0);
                const compHue = (accentHue + 180) % 360; // Complementary color
                gradient.addColorStop(0, `hsl(${accentHue}, 80%, 65%)`);
                gradient.addColorStop(0.25, `hsl(${accentHue}, 90%, 75%)`);
                gradient.addColorStop(0.5, '#ffffff');
                gradient.addColorStop(0.75, `hsl(${compHue}, 70%, 70%)`);
                gradient.addColorStop(1, `hsl(${accentHue}, 80%, 65%)`)
                gradient.addColorStop(1, accentColor);

                // Draw main oscilloscope line with glow
                this.visCtx.shadowColor = accentColor;
                this.visCtx.shadowBlur = 15;
                this.visCtx.strokeStyle = gradient;
                this.visCtx.lineWidth = 2.5;
                this.visCtx.beginPath();
                this.drawSmoothCurve(currentPoints, false);
                this.visCtx.stroke();

                // Draw mirrored line (below center)
                this.visCtx.shadowBlur = 10;
                this.visCtx.lineWidth = 1.5;
                this.visCtx.globalAlpha = 0.4;
                this.visCtx.beginPath();
                this.drawSmoothCurve(currentPoints, true);
                this.visCtx.stroke();

                // Reset
                this.visCtx.shadowBlur = 0;
                this.visCtx.globalAlpha = 1;
            }
        };

        draw();
    }

    // Helper: Draw smooth bezier curve through points
    drawSmoothCurve(points, mirror = false) {
        if (points.length < 2) return;

        const height = this.visualizer.height / window.devicePixelRatio;
        const centerY = height / 2;

        // Transform Y for mirroring
        const getY = (y) => mirror ? centerY + (centerY - y) : y;

        this.visCtx.moveTo(points[0].x, getY(points[0].y));

        for (let i = 1; i < points.length - 1; i++) {
            const xc = (points[i].x + points[i + 1].x) / 2;
            const yc = (getY(points[i].y) + getY(points[i + 1].y)) / 2;
            this.visCtx.quadraticCurveTo(points[i].x, getY(points[i].y), xc, yc);
        }

        // Last point
        const last = points[points.length - 1];
        this.visCtx.lineTo(last.x, getY(last.y));
    }

    // === Auto Load ===

    async autoLoadSongs() {
        // Use server-injected data if available (Server-Side Caching)
        if (window.INITIAL_SONGS && window.INITIAL_SONGS.length > 0) {
            console.log('Loaded songs from server injection');
            this.songs = window.INITIAL_SONGS;
            this.baseNames = window.INITIAL_BASE_NAMES || [];
            this.populateModeSelect();
            this.startBtn.disabled = false;
            // Hide loading indicator immediately
            if (this.loadingIndicator) {
                this.loadingIndicator.style.display = 'none';
            }
            return;
        }

        if (this.loadingIndicator) {
            this.loadingIndicator.style.display = 'block';
        }

        try {
            // First try to get existing songs via API if injection missing/empty
            const response = await fetch('/api/songs');
            const data = await response.json();

            if (data.songs && data.songs.length > 0) {
                this.songs = data.songs;
                this.baseNames = data.base_names || [];

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
        // Animate out the current song
        if (this.songName) {
            this.songName.style.animation = 'slideOut 0.2s ease-in forwards';
        }

        setTimeout(() => {
            this.currentIndex++;

            if (this.currentIndex >= this.queue.length) {
                this.showFeedback('All songs rated!');
                this.setupSection.style.display = 'block';
                this.playerSection.style.display = 'none';
                if (this.pageTitle) this.pageTitle.textContent = 'Song Voter';
                return;
            }

            this.loadSong(this.queue[this.currentIndex]);

            // Animate in the new song
            if (this.songName) {
                this.songName.style.animation = 'slideIn 0.3s ease-out forwards';
            }
        }, 200);
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
        this.updateRating(); // Initialize rating color

        // Reset listening time tracking
        this.stopListenTimer();
        this.listenedTime = 0;
        this.lastTimeUpdate = 0;
        this.updateSubmitButtonState();

        // Load audio
        this.audio.src = `/api/songs/${song.id}/audio`;
        this.audio.load();

        // Fetch waveform
        this.waveData = null;
        fetch(`/api/songs/${song.id}/waveform`)
            .then(res => res.json())
            .then(data => {
                this.waveData = data;
                this.drawWaveform();
            })
            .catch(() => this.waveData = null);

        // Load audio
        this.audio.src = `/api/songs/${song.id}/audio`;
        this.audio.load();

        // Fetch waveform
        this.waveData = null;
        fetch(`/api/songs/${song.id}/waveform`)
            .then(res => res.json())
            .then(data => {
                this.waveData = data;
                this.drawWaveform();
            })
            .catch(() => this.waveData = null);

        this.audio.play().catch(err => console.log('Autoplay blocked:', err));
    }

    async togglePlay() {
        if (this.isPlaying) {
            this.audio.pause();
        } else {
            // Ensure AudioContext is running BEFORE playing audio
            if (this.audioContext && this.audioContext.state !== 'running') {
                try {
                    await this.audioContext.resume();
                    console.log('AudioContext resumed before play');
                } catch (err) {
                    console.log('AudioContext resume failed:', err);
                }
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
        if (!this.waveformCanvas) return;
        this.currentTime.textContent = this.formatTime(this.audio.currentTime);
        // Drawing happens in animation loop now for smoothness

        // Update submit button state (timer is handled separately)
        this.updateSubmitButtonState();
    }

    animateWaveform() {
        this.drawWaveform();
        requestAnimationFrame(() => this.animateWaveform());
    }

    drawWaveform() {
        if (!this.waveCtx || !this.waveformCanvas) return;

        const width = this.waveformCanvas.offsetWidth;
        const height = this.waveformCanvas.offsetHeight;

        // Handle retina if size changed
        if (this.waveformCanvas.width !== width * window.devicePixelRatio) {
            this.waveformCanvas.width = width * window.devicePixelRatio;
            this.waveformCanvas.height = height * window.devicePixelRatio;
            this.waveCtx.scale(window.devicePixelRatio, window.devicePixelRatio);
        }

        // Clear (transparent background)
        this.waveCtx.clearRect(0, 0, width, height);

        // Use dummy data if not loaded yet
        const data = this.waveData || new Array(100).fill(0.005);
        const barWidth = width / data.length;
        const gap = 0.5; // Small gap

        const progress = this.audio.currentTime / this.audio.duration || 0;
        const progressX = progress * width;

        // Use cached accent color
        const accentColor = this.accentColor || '#ffffff';

        // 1. Draw Unplayed Bars (Base Layer)
        this.waveCtx.shadowBlur = 0;
        this.waveCtx.fillStyle = 'rgba(255, 255, 255, 0.15)';
        for (let i = 0; i < data.length; i++) {
            const val = data[i];
            const x = i * barWidth;
            const barHeight = Math.max(2, val * height);
            const y = (height - barHeight) / 2;
            this.waveCtx.fillRect(x, y, barWidth - gap, barHeight);
        }

        // 2. Draw Hover Overlay (if hovering beyond progress)
        if (this.hoverX > progressX) {
            this.waveCtx.save();
            this.waveCtx.beginPath();
            this.waveCtx.rect(progressX, 0, this.hoverX - progressX, height);
            this.waveCtx.clip();

            this.waveCtx.fillStyle = 'rgba(255, 255, 255, 0.5)';
            for (let i = 0; i < data.length; i++) {
                const val = data[i];
                const x = i * barWidth;
                if (x + barWidth < progressX) continue; // optimization
                const barHeight = Math.max(2, val * height);
                const y = (height - barHeight) / 2;
                this.waveCtx.fillRect(x, y, barWidth - gap, barHeight);
            }
            this.waveCtx.restore();
        }

        // 3. Draw Played Portion (Clipped with Glow)
        this.waveCtx.save();
        this.waveCtx.beginPath();
        this.waveCtx.rect(0, 0, progressX, height);
        this.waveCtx.clip();

        // Create gradient for played portion
        const playedGradient = this.waveCtx.createLinearGradient(0, 0, progressX, 0);
        playedGradient.addColorStop(0, 'rgba(255, 255, 255, 0.9)');
        playedGradient.addColorStop(1, accentColor);

        this.waveCtx.shadowColor = accentColor;
        this.waveCtx.shadowBlur = 2;  // Subtle glow
        this.waveCtx.fillStyle = playedGradient;

        for (let i = 0; i < data.length; i++) {
            const val = data[i];
            const x = i * barWidth;
            if (x > progressX) break; // optimization
            const barHeight = Math.max(2, val * height);
            const y = (height - barHeight) / 2;
            this.waveCtx.fillRect(x, y, barWidth - gap, barHeight);
        }
        this.waveCtx.restore();

        // Draw playhead line
        if (progress > 0 && progress < 1) {
            this.waveCtx.shadowBlur = 4;  // Subtle glow
            this.waveCtx.shadowColor = accentColor;
            this.waveCtx.strokeStyle = '#ffffff';
            this.waveCtx.lineWidth = 2;
            this.waveCtx.beginPath();
            this.waveCtx.moveTo(progressX, 0);
            this.waveCtx.lineTo(progressX, height);
            this.waveCtx.stroke();
            this.waveCtx.shadowBlur = 0;
        }
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

        // Haptic feedback
        if (navigator.vibrate) navigator.vibrate(15);
    }

    updateRating() {
        const value = parseInt(this.ratingSlider.value);
        this.ratingValue.textContent = value;

        // Color gradient: red (1) -> yellow (5) -> green (10)
        let r, g, b;
        if (value <= 5) {
            // Red to yellow (1-5)
            const t = (value - 1) / 4;
            r = 220;
            g = Math.round(60 + t * 160); // 60 -> 220
            b = 60;
        } else {
            // Yellow to green (6-10)
            const t = (value - 5) / 5;
            r = Math.round(220 - t * 140); // 220 -> 80
            g = Math.round(220 - t * 20); // 220 -> 200
            b = Math.round(60 + t * 40); // 60 -> 100
        }
        this.ratingValue.style.color = `rgb(${r}, ${g}, ${b})`;

        // Haptic feedback on significant changes
        if (navigator.vibrate && (value === 1 || value === 5 || value === 10)) {
            navigator.vibrate(10);
        }
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
            this.showFeedback('Network error', true);
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
        }, 3000);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.songVoter = new SongVoter();
});
