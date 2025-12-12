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

            // Start with global config
            this.minListenTime = config.min_listen_time || 20;
            this.disableSkip = config.disable_skip || false;

            // Block-specific overrides (if set, they take precedence)
            if (window.BLOCK_MODE) {
                if (window.BLOCK_MIN_LISTEN_TIME !== null && window.BLOCK_MIN_LISTEN_TIME !== undefined) {
                    this.minListenTime = window.BLOCK_MIN_LISTEN_TIME;
                    console.log('Using block-specific min listen time:', this.minListenTime);
                }
                if (window.BLOCK_DISABLE_SKIP !== null && window.BLOCK_DISABLE_SKIP !== undefined) {
                    this.disableSkip = window.BLOCK_DISABLE_SKIP === 1 || window.BLOCK_DISABLE_SKIP === true;
                    console.log('Using block-specific disable skip:', this.disableSkip);
                }
            }

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

        // Preload next song for instant transitions
        this.preloadAudio = new Audio();
        this.preloadAudio.preload = 'auto';
        this.preloadedSongId = null;

        // Draft votes (auto-save to localStorage)
        this.draftKey = 'song_voter_draft';

        // Restore saved volume preference
        const savedVolume = localStorage.getItem('song_voter_volume');
        if (savedVolume !== null && this.volumeSlider) {
            this.volumeSlider.value = savedVolume;
            this.audio.volume = savedVolume / 100;
        }
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
            this.waveformDirty = true; // Trigger redraw on hover
        });
        this.waveformCanvas.addEventListener('mouseleave', () => {
            this.hoverX = -1;
            this.waveformDirty = true; // Trigger redraw when leaving
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
            }
            // Note: AudioContext resume is now handled in togglePlay() with await
            // to prevent race conditions that cause audio lag
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

        // Check if Cast is enabled via admin settings
        if (!window.CAST_ENABLED || !window.CAST_APP_ID) {
            // Fall back to Remote Playback API if Cast SDK not configured
            if ('remote' in this.audio) {
                this.audio.remote.watchAvailability((available) => {
                    this.castBtn.style.display = available ? 'inline-flex' : 'none';
                }).catch(() => {
                    this.castBtn.style.display = 'inline-flex';
                });
            } else {
                this.castBtn.style.display = 'none';
            }
            return;
        }

        // Show cast button immediately if enabled (SDK manages state later)
        this.castBtn.style.display = 'inline-flex';

        console.log('Initializing Cast with:', {
            enabled: window.CAST_ENABLED,
            appId: window.CAST_APP_ID,
            type: window.CAST_RECEIVER_TYPE
        });

        // Load Cast SDK dynamically
        this.loadCastSDK().then(() => {
            this.initCastContext();
        }).catch(err => {
            console.log('Cast SDK load failed, falling back to Remote Playback:', err);
            // Fallback to Remote Playback API
            this.useFallbackCast = true;
            this.castBtn.style.display = 'inline-flex';
        });
    }

    loadCastSDK() {
        return new Promise((resolve, reject) => {
            // Check if already loaded
            if (window.cast && window.cast.framework) {
                resolve();
                return;
            }

            // Load the Cast SDK
            const script = document.createElement('script');
            script.src = 'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1';
            script.async = true;

            window['__onGCastApiAvailable'] = (isAvailable) => {
                if (isAvailable) {
                    resolve();
                } else {
                    reject(new Error('Cast API not available'));
                }
            };

            script.onerror = () => reject(new Error('Failed to load Cast SDK'));
            document.head.appendChild(script);
        });
    }

    initCastContext() {
        const castContext = cast.framework.CastContext.getInstance();

        // Determine receiver application ID
        let receiverAppId = window.CAST_APP_ID;
        if (window.CAST_RECEIVER_TYPE === 'default') {
            receiverAppId = chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID;
        }

        castContext.setOptions({
            receiverApplicationId: receiverAppId,
            autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED
        });

        // Listen for cast state changes (device availability)
        castContext.addEventListener(
            cast.framework.CastContextEventType.CAST_STATE_CHANGED,
            (event) => {
                console.log('Cast state:', event.castState);
                // Show button when cast devices are available or connected
                if (event.castState !== cast.framework.CastState.NO_DEVICES_AVAILABLE) {
                    this.castBtn.style.display = 'inline-flex';
                }
            }
        );

        // Listen for session state changes
        castContext.addEventListener(
            cast.framework.CastContextEventType.SESSION_STATE_CHANGED,
            (event) => this.onCastSessionStateChanged(event)
        );

        // Store reference
        this.castContext = castContext;
        this.castReady = true;

        // Check initial state - may already have devices
        const initialState = castContext.getCastState();
        console.log('Initial cast state:', initialState);
        if (initialState !== cast.framework.CastState.NO_DEVICES_AVAILABLE) {
            this.castBtn.style.display = 'inline-flex';
        }
    }

    onCastSessionStateChanged(event) {
        const session = cast.framework.CastContext.getInstance().getCurrentSession();

        switch (event.sessionState) {
            case cast.framework.SessionState.SESSION_STARTED:
            case cast.framework.SessionState.SESSION_RESUMED:
                this.castSession = session;
                this.castBtn.classList.add('casting');
                this.castBtn.title = 'Casting...';
                // Load current media to cast device
                if (this.currentSong) {
                    this.loadMediaToCast();
                }
                break;

            case cast.framework.SessionState.SESSION_ENDED:
                this.castSession = null;
                this.castBtn.classList.remove('casting');
                this.castBtn.title = 'Cast';
                break;
        }
    }

    loadMediaToCast() {
        if (!this.castSession || !this.currentSong) return;

        const mediaInfo = new chrome.cast.media.MediaInfo(
            window.location.origin + `/api/songs/${this.currentSong.id}/audio`,
            'audio/mpeg'
        );

        // Add metadata for display on TV
        mediaInfo.metadata = new chrome.cast.media.MusicTrackMediaMetadata();
        mediaInfo.metadata.title = this.currentSong.base_name || this.currentSong.filename;
        mediaInfo.metadata.artist = window.SITE_TITLE || 'Song Voter';

        // Add OG image if available
        if (window.OG_IMAGE) {
            const ogImageUrl = window.OG_IMAGE.startsWith('http')
                ? window.OG_IMAGE
                : window.location.origin + window.OG_IMAGE;
            mediaInfo.metadata.images = [new chrome.cast.Image(ogImageUrl)];
        }

        // Add waveform URL for visualizer on receiver
        mediaInfo.customData = {
            waveformUrl: window.location.origin + `/api/songs/${this.currentSong.id}/waveform`
        };

        const request = new chrome.cast.media.LoadRequest(mediaInfo);
        request.currentTime = this.audio.currentTime;
        request.autoplay = this.isPlaying;

        this.castSession.loadMedia(request).then(() => {
            console.log('Media loaded to cast device');
            // Sync volume after media loads
            setTimeout(() => this.setCastVolume(), 500);
        }).catch(err => {
            console.log('Cast media load error:', err);
        });
    }

    setCastVolume() {
        if (!this.castSession) return;

        // Get volume from slider (0-100 range, convert to 0-1)
        const volume = this.volumeSlider ? this.volumeSlider.value / 100 : 1;

        try {
            this.castSession.setVolume(volume);
            console.log('Cast volume set to:', volume);
        } catch (err) {
            console.log('Cast volume error:', err);
        }
    }

    promptCast() {
        // If SDK not ready yet, try Remote Playback API
        if (!this.castReady || this.useFallbackCast) {
            if ('remote' in this.audio) {
                this.audio.remote.prompt().catch(err => {
                    console.log('Cast prompt error:', err);
                });
            }
            return;
        }

        // Use Cast SDK
        if (this.castContext) {
            // requestSession must be called synchronously from user gesture
            try {
                this.castContext.requestSession();
            } catch (err) {
                console.log('Cast session error:', err);
                // Fallback: try Remote Playback API
                if ('remote' in this.audio) {
                    this.audio.remote.prompt().catch(e => console.log('Fallback cast error:', e));
                }
            }
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
            this.analyser.fftSize = 256; // Higher for smoother oscilloscope

            // Pre-allocate typed arrays once (performance optimization)
            const bufferLength = this.analyser.frequencyBinCount;
            this.dataArray = new Uint8Array(bufferLength);
            this.frequencyData = new Uint8Array(bufferLength);

            // Cache visualizer hue (avoid parsing color every frame)
            const visualizerColor = window.VISUALIZER_COLOR || '';
            if (visualizerColor && visualizerColor !== '') {
                const vHex = visualizerColor.replace('#', '');
                const vr = parseInt(vHex.substr(0, 2), 16) / 255;
                const vg = parseInt(vHex.substr(2, 2), 16) / 255;
                const vb = parseInt(vHex.substr(4, 2), 16) / 255;
                const vmax = Math.max(vr, vg, vb), vmin = Math.min(vr, vg, vb);
                let vh = 0;
                if (vmax !== vmin) {
                    const vd = vmax - vmin;
                    if (vmax === vr) vh = ((vg - vb) / vd + (vg < vb ? 6 : 0)) / 6;
                    else if (vmax === vg) vh = ((vb - vr) / vd + 2) / 6;
                    else vh = ((vr - vg) / vd + 4) / 6;
                }
                this.visualizerHue = Math.round(vh * 360);
            } else {
                // Default: Classic VU meter green
                this.visualizerHue = 120;
            }

            // Detect low-power device for reduced complexity
            this.isLowPowerDevice = (navigator.hardwareConcurrency || 4) <= 4;

            // Create gain node for volume control AFTER analyser
            this.gainNode = this.audioContext.createGain();
            this.gainNode.gain.value = this.volumeSlider ? this.volumeSlider.value / 100 : 1;

            const source = this.audioContext.createMediaElementSource(this.audio);
            // Route: source -> analyser -> gainNode -> destination
            // This way analyser sees full amplitude, gain controls output
            source.connect(this.analyser);
            this.analyser.connect(this.gainNode);
            this.gainNode.connect(this.audioContext.destination);

            // Disable HTML5 audio volume (we use gainNode now)
            this.audio.volume = 1;

            this.drawVisualizer();
        } catch (err) {
            console.log('Visualizer setup failed:', err);
        }
    }

    drawVisualizer() {
        if (!this.analyser || !this.visCtx) return;

        const mode = window.VISUALIZER_MODE || 'bars';

        // Trail history for ghost effect (moved outside draw loop but kept in closure)
        const trailHistory = [];
        const maxTrails = this.isLowPowerDevice ? 2 : 5;

        // Use cached hue from setup
        const accentHue = this.visualizerHue || 120;
        const isDefaultAccent = !window.VISUALIZER_COLOR;

        // Bar count based on device capability
        const barCount = this.isLowPowerDevice ? 32 : 64;

        const draw = () => {
            // Store RAF ID so we can cancel it when paused
            this.visualizerRAF = requestAnimationFrame(draw);

            // Skip drawing when paused (major performance win)
            if (!this.isPlaying) {
                return;
            }

            const width = this.visualizer.width / window.devicePixelRatio;
            const height = this.visualizer.height / window.devicePixelRatio;

            // Clear for fully transparent background (shows card through)
            this.visCtx.clearRect(0, 0, width, height);

            // Get appropriate data using pre-allocated arrays
            this.analyser.getByteTimeDomainData(this.dataArray);
            this.analyser.getByteFrequencyData(this.frequencyData);

            const bufferLength = this.dataArray.length;

            // Draw bars first if mode is 'bars' or 'both'
            if (mode === 'bars' || mode === 'both') {
                const barWidth = (width / barCount) * 0.85;
                const gap = (width / barCount) * 0.15;

                for (let i = 0; i < barCount; i++) {
                    const idx = Math.floor(i * bufferLength / barCount);
                    const value = this.frequencyData[idx] / 255;
                    const barHeight = value * height * 0.9;
                    const x = i * (barWidth + gap);

                    // Green audio equipment gradient - lime to teal
                    const hueSpread = isDefaultAccent ? 60 : 50;
                    const hueOffset = (i / barCount) * hueSpread - (hueSpread / 2);
                    const barHue = (accentHue + hueOffset + 360) % 360;

                    if (mode === 'both') {
                        // In both mode: bars are a subtle glowing backdrop
                        const sat = 30 + value * 40;
                        const light = 20 + value * 30;

                        // Skip gradient on low-power devices
                        if (this.isLowPowerDevice) {
                            this.visCtx.fillStyle = `hsla(${barHue}, ${sat}%, ${light}%, 0.5)`;
                        } else {
                            const barGrad = this.visCtx.createLinearGradient(0, height, 0, height - barHeight);
                            barGrad.addColorStop(0, `hsla(${barHue}, ${sat}%, ${light}%, 0.6)`);
                            barGrad.addColorStop(1, `hsla(${barHue}, ${sat}%, ${light}%, 0.15)`);
                            this.visCtx.fillStyle = barGrad;
                        }
                    } else {
                        // Bars-only mode: full vibrant bars
                        const sat = 50 + value * 40;
                        const light = 35 + value * 40;
                        this.visCtx.fillStyle = `hsla(${barHue}, ${sat}%, ${light}%, 0.85)`;
                    }
                    this.visCtx.fillRect(x, height - barHeight, barWidth, barHeight);
                }
            }

            // Draw oscilloscope if mode is 'wave' or 'both'
            if (mode === 'wave' || mode === 'both') {
                // Calculate average amplitude for reactive effects
                let avgAmplitude = 0;
                for (let i = 0; i < bufferLength; i++) {
                    avgAmplitude += Math.abs(this.dataArray[i] - 128);
                }
                avgAmplitude = (avgAmplitude / bufferLength) / 128; // 0-1 range

                // Store current frame points for trails
                const currentPoints = [];
                // Use (bufferLength - 1) so last point reaches exactly width
                const sliceWidth = width / (bufferLength - 1);

                for (let i = 0; i < bufferLength; i++) {
                    const v = this.dataArray[i] / 128.0;
                    const y = (v * height) / 2;
                    currentPoints.push({ x: i * sliceWidth, y });
                }

                // Add to trail history
                trailHistory.unshift(currentPoints);
                if (trailHistory.length > maxTrails) trailHistory.pop();

                // Green oscilloscope: classic VU green → electric blue complement
                const baseHue = accentHue;

                // Draw trails (oldest to newest, fading) - Green VU gradient
                // Skip trails on low-power devices
                if (!this.isLowPowerDevice) {
                    for (let t = trailHistory.length - 1; t >= 0; t--) {
                        const points = trailHistory[t];
                        const trailAlpha = (1 - t / maxTrails) * 0.2;

                        if (t > 0) {
                            this.visCtx.strokeStyle = `hsla(${baseHue}, 60%, 50%, ${trailAlpha})`;
                            this.visCtx.lineWidth = 1;
                            this.visCtx.beginPath();
                            this.drawSmoothCurve(points, false);
                            this.visCtx.stroke();
                        }
                    }
                }

                // In 'both' mode, reduce oscilloscope prominence so bars show through
                const isBothMode = mode === 'both';
                const lineOpacity = isBothMode ? 0.7 : 1;
                // Reduce glow on low-power devices
                const glowStrength = this.isLowPowerDevice ? 0 : (isBothMode ? 4 : 8);

                // Green VU gradient for oscilloscope
                const gradient = this.visCtx.createLinearGradient(0, 0, width, 0);
                const satBoost = 65 + avgAmplitude * 25;
                const lightBoost = 45 + avgAmplitude * 30;
                gradient.addColorStop(0, `hsl(${baseHue - 15}, ${satBoost}%, ${lightBoost}%)`);
                gradient.addColorStop(0.5, `hsl(${baseHue}, ${satBoost + 10}%, ${lightBoost + 10}%)`);
                gradient.addColorStop(1, `hsl(${baseHue + 15}, ${satBoost}%, ${lightBoost}%)`);

                // Draw main oscilloscope line with green glow
                this.visCtx.globalAlpha = lineOpacity;
                if (glowStrength > 0) {
                    this.visCtx.shadowColor = `hsl(${baseHue}, 60%, 50%)`;
                    this.visCtx.shadowBlur = glowStrength;
                }
                this.visCtx.strokeStyle = gradient;
                this.visCtx.lineWidth = isBothMode ? 1.5 + avgAmplitude * 0.5 : 2 + avgAmplitude;
                this.visCtx.beginPath();
                this.drawSmoothCurve(currentPoints, false);
                this.visCtx.stroke();

                // Draw mirrored line (below center) - subtle green (skip on low-power)
                if (!this.isLowPowerDevice) {
                    this.visCtx.strokeStyle = `hsla(${baseHue}, 50%, 40%, 0.3)`;
                    this.visCtx.shadowBlur = 2;
                    this.visCtx.lineWidth = 1;
                    this.visCtx.globalAlpha = 0.3;
                    this.visCtx.beginPath();
                    this.drawSmoothCurve(currentPoints, true);
                    this.visCtx.stroke();
                }

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
        // In block mode, use all songs; otherwise use mode selector
        if (window.BLOCK_MODE) {
            this.mode = 'all';
            this.queue = [...this.songs];
        } else {
            this.mode = this.modeSelect ? this.modeSelect.value : 'all';

            if (this.mode === 'all') {
                this.queue = [...this.songs];
            } else {
                this.queue = this.songs.filter(s => s.base_name === this.mode);
            }
        }


        // Shuffle (Fisher-Yates algorithm - different order for each visitor)
        for (let i = this.queue.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [this.queue[i], this.queue[j]] = [this.queue[j], this.queue[i]];
        }
        console.log('Shuffled queue order:', this.queue.map(s => s.filename));

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
        // Haptic feedback for tactile response (mobile)
        if (navigator.vibrate) {
            navigator.vibrate(15);
        }

        // Fade out waveform FIRST for smooth transition
        if (this.waveformCanvas) {
            this.waveformCanvas.style.transition = 'opacity 0.25s ease-out';
            this.waveformCanvas.style.opacity = '0';
        }

        // Animate out the current song with more visual weight
        const card = document.querySelector('.card');
        if (this.songName) {
            this.songName.style.animation = 'slideOut 0.25s ease-in forwards';
        }
        if (card) {
            card.style.transition = 'transform 0.25s ease-in, opacity 0.25s ease-in';
            card.style.transform = 'scale(0.95) translateX(-20px)';
            card.style.opacity = '0.7';
        }
        if (this.visualizer) {
            this.visualizer.style.transition = 'opacity 0.15s ease-out';
            this.visualizer.style.opacity = '0.3';
        }

        setTimeout(() => {
            this.currentIndex++;

            if (this.currentIndex >= this.queue.length) {
                // Stop audio playback
                this.audio.pause();
                this.audio.currentTime = 0;
                this.stopListenTimer();

                // Show completion screen
                this.showCompletionScreen();
                return;
            }

            this.loadSong(this.queue[this.currentIndex]);

            // Animate in the new song with more weight
            if (this.songName) {
                this.songName.style.animation = 'slideIn 0.35s ease-out forwards';
            }
            if (card) {
                card.style.transform = 'scale(1.02)';
                card.style.opacity = '1';
                setTimeout(() => {
                    card.style.transition = 'transform 0.2s ease-out';
                    card.style.transform = 'scale(1)';
                }, 100);
            }
            if (this.visualizer) {
                this.visualizer.style.opacity = '1';
            }
        }, 250);
    }

    showCompletionScreen() {
        // Hide player, show completion in the same container
        this.playerSection.style.display = 'none';

        // Create or show completion section
        let completionSection = document.getElementById('completionSection');
        if (!completionSection) {
            completionSection = document.createElement('div');
            completionSection.id = 'completionSection';
            completionSection.className = 'card';
            completionSection.innerHTML = `
                <div style="text-align: center; padding: 32px 16px;">
                    <div style="font-size: 2.5rem; margin-bottom: 16px;">✓</div>
                    <h2 style="font-size: 1.25rem; font-weight: 500; margin-bottom: 12px; color: var(--text-primary);">
                        Done
                    </h2>
                    <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 24px;">
                        ${this.queue.length} song${this.queue.length !== 1 ? 's' : ''} rated. Your input shapes the final cut.
                    </p>
                    <div style="width: 60px; height: 2px; background: var(--border); margin: 0 auto;"></div>
                </div>
            `;
            this.setupSection.parentNode.insertBefore(completionSection, this.setupSection.nextSibling);
        } else {
            completionSection.style.display = 'block';
        }

        // Update page title
        if (this.pageTitle) {
            this.pageTitle.textContent = 'Complete';
        }
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

        // Clear waveform data (fade-out already happened in playNext)
        this.waveData = null;

        // Load audio
        this.audio.src = `/api/songs/${song.id}/audio`;
        this.audio.load();

        // Fetch waveform and smoothly fade in once loaded
        fetch(`/api/songs/${song.id}/waveform`)
            .then(res => res.json())
            .then(data => {
                this.waveData = data;
                this.drawWaveform();
                // Fade in waveform after data is ready
                if (this.waveformCanvas) {
                    this.waveformCanvas.style.transition = 'opacity 0.5s ease-in';
                    this.waveformCanvas.style.opacity = '1';
                }
            })
            .catch(() => this.waveData = null);

        this.audio.play().catch(err => console.log('Autoplay blocked:', err));

        // Update cast device with new song
        if (this.castSession) {
            this.loadMediaToCast();
        }

        // Preload next song for instant transition
        this.preloadNextSong();

        // Restore any draft vote for this song
        this.restoreDraft();
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
        // Haptic feedback for seek
        if (navigator.vibrate) navigator.vibrate(5);
    }

    setVolume() {
        const volume = this.volumeSlider.value / 100;
        // Use gainNode if available (for decoupled visualization)
        if (this.gainNode) {
            this.gainNode.gain.value = volume;
        } else {
            this.audio.volume = volume;
        }
        // Persist volume preference
        localStorage.setItem('song_voter_volume', this.volumeSlider.value);

        // Sync volume to cast device if active
        this.setCastVolume();
    }

    updateProgress() {
        if (!this.waveformCanvas) return;
        this.currentTime.textContent = this.formatTime(this.audio.currentTime);

        // Mark waveform as needing redraw
        this.waveformDirty = true;

        // Update submit button state (timer is handled separately)
        this.updateSubmitButtonState();
    }

    animateWaveform() {
        // Only draw if playing OR if dirty (seek/hover)
        if (this.isPlaying || this.waveformDirty) {
            this.drawWaveform();
            this.waveformDirty = false;
        }
        this.waveformRAF = requestAnimationFrame(() => this.animateWaveform());
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

        // Auto-save draft
        this.saveDraft();
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

        // Haptic ticks on every value change
        if (navigator.vibrate) {
            // Stronger vibration at boundaries (1, 5, 10)
            if (value === 1 || value === 5 || value === 10) {
                navigator.vibrate(8);
            } else {
                navigator.vibrate(3); // Subtle tick for each value
            }
        }

        // Auto-save draft
        this.saveDraft();
    }

    async submitVote() {
        if (!this.currentSong) return;

        this.submitBtn.disabled = true;
        const rating = parseInt(this.ratingSlider.value);

        // Build vote payload
        const payload = {
            thumbs_up: this.thumbsValue,
            rating: rating
        };

        // Include block_id when voting in block mode
        if (window.BLOCK_MODE && window.BLOCK_ID) {
            payload.block_id = window.BLOCK_ID;
        }

        try {
            const response = await fetch(`/api/songs/${this.currentSong.id}/vote`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });


            const data = await response.json();

            if (data.success) {
                // Vote pulse animation
                const card = document.querySelector('.card');
                if (card) {
                    card.classList.add('vote-pulse');
                    setTimeout(() => card.classList.remove('vote-pulse'), 600);
                }
                // Haptic success
                if (navigator.vibrate) navigator.vibrate([10, 50, 10]);

                // Clear draft after successful submission
                this.clearDraft();

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

    // Preload next song in queue for instant transitions
    preloadNextSong() {
        const nextIndex = this.currentIndex + 1;
        if (nextIndex < this.queue.length) {
            const nextSong = this.queue[nextIndex];
            this.preloadAudio.src = `/api/songs/${nextSong.id}/audio`;
            this.preloadAudio.load();
            this.preloadedSongId = nextSong.id;
        }
    }

    // Save draft vote to localStorage
    saveDraft() {
        if (!this.currentSong) return;
        const draft = {
            songId: this.currentSong.id,
            thumbs: this.thumbsValue,
            rating: parseInt(this.ratingSlider.value),
            timestamp: Date.now()
        };
        localStorage.setItem(this.draftKey, JSON.stringify(draft));
    }

    // Restore draft vote if available
    restoreDraft() {
        if (!this.currentSong) return false;
        try {
            const draft = JSON.parse(localStorage.getItem(this.draftKey));
            if (draft && draft.songId === this.currentSong.id) {
                // Restore thumbs
                if (draft.thumbs === true) {
                    this.setThumb(true);
                } else if (draft.thumbs === false) {
                    this.setThumb(false);
                }
                // Restore rating
                if (draft.rating) {
                    this.ratingSlider.value = draft.rating;
                    this.updateRating();
                }
                return true;
            }
        } catch (e) {
            // Invalid draft, ignore
        }
        return false;
    }

    // Clear draft after successful submission
    clearDraft() {
        localStorage.removeItem(this.draftKey);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.songVoter = new SongVoter();
});
