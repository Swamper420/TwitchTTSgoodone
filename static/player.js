document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const audioPlayer = document.getElementById('audioPlayer');
    const audioUnlockOverlay = document.getElementById('audioUnlockOverlay');
    const enableAudioBtn = document.getElementById('enableAudioBtn');
    
    const statusPill = document.getElementById('statusPill');
    const statusText = document.getElementById('statusText');
    const queueBadge = document.getElementById('queueBadge');
    
    const speakerAvatar = document.getElementById('speakerAvatar');
    const currentSpeaker = document.getElementById('currentSpeaker');
    const currentText = document.getElementById('currentText');
    const voiceTag = document.getElementById('voiceTag');
    const chunkTag = document.getElementById('chunkTag');
    
    const equalizerVisualizer = document.getElementById('equalizerVisualizer');
    const spectrumCanvas = document.getElementById('spectrumCanvas');
    const canvasCtx = spectrumCanvas ? spectrumCanvas.getContext('2d') : null;
    
    const skipBtn = document.getElementById('skipBtn');
    const muteBtn = document.getElementById('muteBtn');
    const volumeSlider = document.getElementById('volumeSlider');
    const volumeValue = document.getElementById('volumeValue');
    const chimeToggle = document.getElementById('chimeToggle');
    const overlayModeBtn = document.getElementById('overlayModeBtn');
    const overlayBtnText = document.getElementById('overlayBtnText');
    
    const voiceHistoryFeed = document.getElementById('voiceHistoryFeed');
    const historyCount = document.getElementById('historyCount');

    // Constants
    const SILENT_WAV = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==';
    
    // Player State
    let audioQueue = [];
    let isPlaying = false;
    let currentItem = null;
    let playedCount = 0;
    let audioUnlocked = false;

    // Web Audio API State
    let audioCtx = null;
    let analyser = null;
    let audioSource = null;
    let animFrameId = null;

    // URL Query Parameters check (OBS Overlay Mode)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'overlay' || urlParams.has('transparent') || urlParams.get('obs') === '1') {
        document.body.classList.add('overlay-mode');
        if (overlayBtnText) overlayBtnText.textContent = 'Normal Mode';
    }
    if (urlParams.get('autostart') === '1' || urlParams.get('autostart') === 'true') {
        unlockAudio();
    }

    // Load persisted settings
    const savedVol = localStorage.getItem('tts_player_volume');
    if (savedVol !== null && volumeSlider && volumeValue) {
        const val = parseInt(savedVol, 10);
        volumeSlider.value = val;
        volumeValue.textContent = `${val}%`;
        audioPlayer.volume = val / 100;
    } else if (volumeSlider) {
        audioPlayer.volume = 0.8;
    }

    const savedChime = localStorage.getItem('tts_player_chime');
    if (savedChime !== null && chimeToggle) {
        chimeToggle.checked = savedChime === 'true';
    }

    // Helper: Safe HTML Escaping (DOM XSS Protection)
    function escapeHTML(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Web Audio API Initialization
    function initWebAudio() {
        if (audioCtx) {
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
            return;
        }
        try {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;
            audioSource = audioCtx.createMediaElementSource(audioPlayer);
            audioSource.connect(analyser);
            analyser.connect(audioCtx.destination);
            renderSpectrum();
        } catch (e) {
            console.log('Web Audio setup note:', e);
        }
    }

    // Unlock Audio Autoplay Policy
    function unlockAudio() {
        if (audioUnlocked) return;
        audioUnlocked = true;

        initWebAudio();
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        if (audioUnlockOverlay) {
            audioUnlockOverlay.classList.add('hidden');
        }

        // Play silent sound to unlock browser audio thread
        try {
            audioPlayer.src = SILENT_WAV;
            audioPlayer.play().then(() => {
                audioPlayer.pause();
            }).catch(() => {});
        } catch (e) {}

        if (!isPlaying && audioQueue.length > 0) {
            checkAndPlayNext();
        }
    }

    if (enableAudioBtn) {
        enableAudioBtn.addEventListener('click', unlockAudio);
    }

    // Notification Chime Sound (Gentle Dual Beep)
    function playNotificationChime() {
        if (!chimeToggle || !chimeToggle.checked) return;
        try {
            const ctx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
            const now = ctx.currentTime;
            
            const osc1 = ctx.createOscillator();
            const gain1 = ctx.createGain();
            osc1.type = 'sine';
            osc1.frequency.setValueAtTime(587.33, now); // D5
            gain1.gain.setValueAtTime(0.08, now);
            gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
            osc1.connect(gain1);
            gain1.connect(ctx.destination);
            osc1.start(now);
            osc1.stop(now + 0.15);

            const osc2 = ctx.createOscillator();
            const gain2 = ctx.createGain();
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(880, now + 0.1); // A5
            gain2.gain.setValueAtTime(0.08, now + 0.1);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
            osc2.connect(gain2);
            gain2.connect(ctx.destination);
            osc2.start(now + 0.1);
            osc2.stop(now + 0.3);
        } catch (e) {
            console.log('Chime sound error:', e);
        }
    }

    // Spectrum Visualizer Renderer
    function renderSpectrum() {
        if (!canvasCtx || !analyser) return;

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        function draw() {
            animFrameId = requestAnimationFrame(draw);
            analyser.getByteFrequencyData(dataArray);

            canvasCtx.clearRect(0, 0, spectrumCanvas.width, spectrumCanvas.height);

            const numBars = 20;
            const barGap = 3;
            const step = Math.max(1, Math.floor(bufferLength / numBars));
            const barWidth = Math.max(4, Math.floor((spectrumCanvas.width - (numBars * barGap)) / numBars));

            const blockHeight = 4;
            const blockGap = 2;
            const maxBlocks = Math.floor(spectrumCanvas.height / (blockHeight + blockGap));

            let x = 0;

            for (let i = 0; i < numBars; i++) {
                let sum = 0;
                for (let j = 0; j < step; j++) {
                    sum += dataArray[i * step + j] || 0;
                }
                const val = sum / step;
                const ratio = val / 255;
                const activeBlocks = Math.round(ratio * maxBlocks);

                for (let b = 0; b < maxBlocks; b++) {
                    const blockY = spectrumCanvas.height - ((b + 1) * (blockHeight + blockGap));

                    if (b < activeBlocks) {
                        canvasCtx.fillStyle = (b >= maxBlocks - 2) ? '#c5d7b5' : '#8ba079';
                    } else {
                        canvasCtx.fillStyle = 'rgba(55, 65, 50, 0.25)';
                    }

                    canvasCtx.fillRect(Math.floor(x), Math.floor(blockY), barWidth, blockHeight);
                }

                x += barWidth + barGap;
            }
        }
        draw();
    }

    // Connect Server-Sent Events (SSE) Stream
    function initSSE() {
        const evtSource = new EventSource('/api/events');

        evtSource.onopen = () => {
            if (statusPill && statusText) {
                statusPill.className = 'status-pill connected';
                statusText.textContent = 'Connected to Stream';
            }
        };

        evtSource.onerror = () => {
            if (statusPill && statusText) {
                statusPill.className = 'status-pill disconnected';
                statusText.textContent = 'Reconnecting...';
            }
        };

        evtSource.addEventListener('status', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (statusPill && statusText) {
                    const conn = data.connected;
                    statusPill.className = `status-pill ${conn ? 'connected' : ''}`;
                    statusText.textContent = conn ? `Connected (${data.channel || 'Twitch'})` : 'Listening for Events';
                }
            } catch (err) {}
        });

        evtSource.addEventListener('audio_chunk', (e) => {
            try {
                const item = JSON.parse(e.data);
                if (!item || !item.url) return;
                
                audioQueue.push(item);
                updateQueueDisplay();
                checkAndPlayNext();
            } catch (err) {
                console.error('Failed to process incoming audio chunk:', err);
            }
        });

        evtSource.addEventListener('skip_audio', () => {
            skipCurrentAudio();
        });

        evtSource.addEventListener('clear_audio', () => {
            audioQueue = [];
            skipCurrentAudio();
            updateQueueDisplay();
        });
    }

    // Update Queue Counter Display
    function updateQueueDisplay() {
        if (queueBadge) {
            const count = audioQueue.length + (isPlaying ? 1 : 0);
            queueBadge.textContent = `${count} in queue`;
        }
    }

    let currentFartBgAudio = null;

    // Sequential Audio Player Logic
    function checkAndPlayNext() {
        if (isPlaying || audioQueue.length === 0) return;

        currentItem = audioQueue.shift();
        updateQueueDisplay();

        isPlaying = true;
        playNotificationChime();

        // Update UI
        if (currentSpeaker) currentSpeaker.textContent = currentItem.user || 'Anonymous';
        if (currentText) currentText.textContent = currentItem.text || '';
        if (voiceTag) voiceTag.textContent = `Voice: ${currentItem.voice || 'Default'}`;
        if (chunkTag) chunkTag.textContent = `Chunk ${currentItem.chunk_index || 1}/${currentItem.total_chunks || 1}`;

        if (speakerAvatar) speakerAvatar.classList.add('active');
        if (equalizerVisualizer) equalizerVisualizer.classList.add('playing');

        // Add to voice history log
        addHistoryItem(currentItem);

        // Parallel Fart Background Audio Playback
        if (currentItem && currentItem.has_fart_bg) {
            try {
                if (currentFartBgAudio) {
                    currentFartBgAudio.pause();
                    currentFartBgAudio = null;
                }
                const fartUrl = currentItem.fart_bg_url || '/api/soundboard/fartbackground';
                currentFartBgAudio = new Audio(fartUrl);
                currentFartBgAudio.volume = (audioPlayer && audioPlayer.volume !== undefined) ? audioPlayer.volume : 1.0;
                currentFartBgAudio.play().catch((err) => {
                    console.warn('Player page fart background audio playback note:', err);
                });
            } catch (err) {
                console.error('Failed to initialize player page fart background audio:', err);
            }
        }

        // Load & Play Audio
        audioPlayer.src = currentItem.url;
        audioPlayer.play().catch((err) => {
            console.warn('Audio playback error (browser autoplay block?):', err);
            if (!audioUnlocked && audioUnlockOverlay) {
                audioUnlockOverlay.classList.remove('hidden');
            }
            onAudioEnded();
        });
    }

    function stopFartBgAudio() {
        if (currentFartBgAudio) {
            try {
                currentFartBgAudio.pause();
                currentFartBgAudio.currentTime = 0;
            } catch (e) {}
            currentFartBgAudio = null;
        }
    }

    function onAudioEnded() {
        isPlaying = false;
        currentItem = null;
        stopFartBgAudio();

        if (speakerAvatar) speakerAvatar.classList.remove('active');
        if (equalizerVisualizer) equalizerVisualizer.classList.remove('playing');

        updateQueueDisplay();

        if (audioQueue.length > 0) {
            setTimeout(checkAndPlayNext, 200);
        } else {
            if (currentSpeaker) currentSpeaker.textContent = 'Idle / Listening';
            if (currentText) currentText.textContent = 'Waiting for incoming voice messages...';
            if (chunkTag) chunkTag.textContent = 'Ready';
        }
    }

    function skipCurrentAudio() {
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
        stopFartBgAudio();
        onAudioEnded();
    }

    audioPlayer.addEventListener('ended', onAudioEnded);
    audioPlayer.addEventListener('error', (e) => {
        console.error('Audio element playback error:', e);
        onAudioEnded();
    });

    // Voice History Logger
    function addHistoryItem(item) {
        if (!voiceHistoryFeed) return;

        const emptyMsg = voiceHistoryFeed.querySelector('.feed-empty');
        if (emptyMsg) emptyMsg.remove();

        playedCount++;
        if (historyCount) historyCount.textContent = `${playedCount} played`;

        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        const el = document.createElement('div');
        el.className = 'history-item';
        el.innerHTML = `
            <div class="history-user">${escapeHTML(item.user || 'Chatter')}</div>
            <div class="history-body">
                <div class="history-text">${escapeHTML(item.text)}</div>
                <div class="history-meta">
                    <span>🎙️ ${escapeHTML(item.voice || 'default')}</span>
                    <span>•</span>
                    <span>${timeStr}</span>
                </div>
            </div>
        `;

        voiceHistoryFeed.prepend(el);

        // Keep last 25 items in DOM
        while (voiceHistoryFeed.children.length > 25) {
            voiceHistoryFeed.removeChild(voiceHistoryFeed.lastChild);
        }
    }

    // UI Event Listeners
    if (skipBtn) {
        skipBtn.addEventListener('click', () => {
            try {
                fetch('/api/queue/skip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user: 'Player' })
                }).catch(() => {});
            } catch (e) {}
            skipCurrentAudio();
        });
    }

    if (volumeSlider && volumeValue) {
        volumeSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value, 10);
            volumeValue.textContent = `${val}%`;
            audioPlayer.volume = val / 100;
            localStorage.setItem('tts_player_volume', val);
        });
    }

    if (muteBtn) {
        muteBtn.addEventListener('click', () => {
            audioPlayer.muted = !audioPlayer.muted;
            muteBtn.textContent = audioPlayer.muted ? '🔇' : '🔊';
        });
    }

    if (chimeToggle) {
        chimeToggle.addEventListener('change', (e) => {
            localStorage.setItem('tts_player_chime', e.target.checked);
        });
    }

    if (overlayModeBtn) {
        overlayModeBtn.addEventListener('click', () => {
            document.body.classList.toggle('overlay-mode');
            const isOverlay = document.body.classList.contains('overlay-mode');
            if (overlayBtnText) {
                overlayBtnText.textContent = isOverlay ? 'Normal Mode' : 'OBS Mode';
            }
        });
    }

    // Initialize SSE
    initSSE();
});
