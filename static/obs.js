document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const audioPlayer = document.getElementById('obsAudioPlayer');
    const overlayCard = document.getElementById('obsOverlayCard');
    const liveText = document.getElementById('obsLiveText');
    
    const obsSpeaker = document.getElementById('obsSpeaker');
    const obsText = document.getElementById('obsText');
    const obsAvatar = document.getElementById('obsAvatar');
    
    const obsCanvas = document.getElementById('obsCanvas');
    const canvasCtx = obsCanvas ? obsCanvas.getContext('2d') : null;

    // Constants
    const SILENT_WAV = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==';

    // Query Parameters
    const params = new URLSearchParams(window.location.search);
    const rawChannel = params.get('channel') || params.get('ch');
    const filterChannel = rawChannel ? rawChannel.toLowerCase().replace(/^#/, '').trim() : null;
    const isAutoHide = params.get('autohide') === '1' || params.get('autohide') === 'true' || params.get('hide_idle') === '1';
    const pos = params.get('position') || params.get('pos') || 'bottom-left';
    const customVol = params.get('volume') ? parseInt(params.get('volume'), 10) : 80;
    const playChime = params.get('chime') !== '0' && params.get('chime') !== 'false';
    const fontSize = params.get('font_size');

    // Apply classes/styles from URL params
    if (isAutoHide) {
        overlayCard.classList.add('autohide-active');
    }
    if (pos) {
        document.body.classList.add(`pos-${pos}`);
    }
    if (fontSize && obsText) {
        obsText.style.fontSize = `${parseInt(fontSize, 10)}px`;
    }
    if (audioPlayer) {
        audioPlayer.volume = Math.max(0, Math.min(100, customVol)) / 100;
    }

    // State
    let audioQueue = [];
    let isPlaying = false;
    let currentItem = null;
    let audioUnlocked = false;
    let chaosMode = false;
    let audioCtx = null;
    let analyser = null;
    let audioSource = null;
    let animFrameId = null;

    // Safe HTML Escaping (DOM XSS Protection)
    function escapeHTML(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Auto-unlock Web Audio API in OBS Browser Source
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
            console.log('OBS Web Audio setup note:', e);
        }
    }

    function silentUnlock() {
        initWebAudio();
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        try {
            audioPlayer.src = SILENT_WAV;
            audioPlayer.play().then(() => {
                audioPlayer.pause();
            }).catch(() => {});
        } catch (e) {}
    }

    // Trigger silent unlock on load for OBS
    silentUnlock();
    document.addEventListener('click', silentUnlock, { once: true });

    // Notification Chime Sound
    function playChimeSound() {
        if (!playChime) return;
        try {
            const ctx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
            const now = ctx.currentTime;
            
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(659.25, now); // E5
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.12); // A5
            gain.gain.setValueAtTime(0.06, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.25);
        } catch (e) {}
    }

    // Real-time Canvas Spectrum Visualizer (Runs only during audio playback)
    let isDrawing = false;
    function renderSpectrum() {
        if (!canvasCtx || !analyser || isDrawing) return;
        isDrawing = true;

        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        function draw() {
            if (!isPlaying && audioQueue.length === 0) {
                canvasCtx.clearRect(0, 0, obsCanvas.width, obsCanvas.height);
                isDrawing = false;
                animFrameId = null;
                return;
            }

            animFrameId = requestAnimationFrame(draw);
            analyser.getByteFrequencyData(dataArray);

            if (obsCanvas.clientWidth && obsCanvas.width !== obsCanvas.clientWidth) {
                obsCanvas.width = obsCanvas.clientWidth;
            }

            canvasCtx.clearRect(0, 0, obsCanvas.width, obsCanvas.height);

            const numBars = 20; // Chunky blocky bar count
            const barGap = 2;   // Horizontal gap between chunky bars
            const step = Math.max(1, Math.floor(bufferLength / numBars));
            const barWidth = Math.max(3, Math.floor((obsCanvas.width - (numBars * barGap)) / numBars));

            const blockHeight = 2; // Vertical pixel block height
            const blockGap = 1;    // Vertical gap between block segments
            const maxBlocks = Math.floor(obsCanvas.height / (blockHeight + blockGap));

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
                    const blockY = obsCanvas.height - ((b + 1) * (blockHeight + blockGap));

                    if (b < activeBlocks) {
                        // Active retro green block
                        canvasCtx.fillStyle = (b >= maxBlocks - 1) ? '#e2f0d9' : ((b >= maxBlocks - 2) ? '#c5d7b5' : '#8ba079');
                    } else {
                        // Dimmed pixel block background trace
                        canvasCtx.fillStyle = 'rgba(55, 65, 50, 0.35)';
                    }

                    canvasCtx.fillRect(Math.floor(x), Math.floor(blockY), barWidth, blockHeight);
                }

                x += barWidth + barGap;
            }
        }
        draw();
    }

    // Connect SSE Event Stream
    function initSSE() {
        const sseUrl = filterChannel ? `/api/events?channel=${encodeURIComponent(filterChannel)}` : '/api/events';
        const evtSource = new EventSource(sseUrl);

        evtSource.onopen = () => {
            if (liveText) liveText.textContent = 'TTS';
        };

        evtSource.onerror = () => {
            if (liveText) liveText.textContent = 'RECONNECTING...';
        };

        evtSource.addEventListener('status', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.config && data.config.enable_chaos_mode !== undefined) {
                    chaosMode = !!data.config.enable_chaos_mode;
                    if (chaosMode) flushChaosQueue();
                }
            } catch (err) {}
        });

        evtSource.addEventListener('chaos_mode_update', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.chaos_mode !== undefined) {
                    chaosMode = !!data.chaos_mode;
                    if (chaosMode) flushChaosQueue();
                }
            } catch (err) {}
        });

        evtSource.addEventListener('audio_chunk', (e) => {
            try {
                const item = JSON.parse(e.data);
                if (!item || !item.url) return;
                
                if (filterChannel) {
                    const chunkChan = item.channel ? String(item.channel).toLowerCase().replace(/^#/, '').trim() : '';
                    if (chunkChan !== filterChannel) {
                        return; // Strict frontend channel isolation guard
                    }
                }

                if (chaosMode) {
                    playChaosAudio(item);
                } else {
                    audioQueue.push(item);
                    checkAndPlayNext();
                }
            } catch (err) {
                console.error('OBS Overlay audio chunk error:', err);
            }
        });

        evtSource.addEventListener('skip_audio', (e) => {
            try {
                const data = e.data ? JSON.parse(e.data) : {};
                if (filterChannel) {
                    const cmdChan = data.channel ? String(data.channel).toLowerCase().replace(/^#/, '').trim() : '';
                    if (cmdChan && cmdChan !== filterChannel) return;
                }
                skipCurrentAudio();
            } catch (err) {
                skipCurrentAudio();
            }
        });

        evtSource.addEventListener('clear_audio', (e) => {
            try {
                const data = e.data ? JSON.parse(e.data) : {};
                if (filterChannel) {
                    const cmdChan = data.channel ? String(data.channel).toLowerCase().replace(/^#/, '').trim() : '';
                    if (cmdChan && cmdChan !== filterChannel) return;
                }
                audioQueue = [];
                skipCurrentAudio();
            } catch (err) {
                audioQueue = [];
                skipCurrentAudio();
            }
        });

        evtSource.addEventListener('soundboard_trigger', (e) => {
            try {
                const data = JSON.parse(e.data);
                if (!data || !data.sound_name) return;
                if (filterChannel) {
                    const cmdChan = data.channel ? String(data.channel).toLowerCase().replace(/^#/, '').trim() : '';
                    if (cmdChan && cmdChan !== filterChannel) return;
                }
                const sbUrl = data.file_path || `/api/soundboard/${data.sound_name}`;
                const isDuplicate = audioQueue.some(q => q.url === sbUrl) || (currentItem && currentItem.url === sbUrl && isPlaying);
                if (!isDuplicate) {
                    audioQueue.push({
                        id: `sb_${data.timestamp || Date.now()}`,
                        url: sbUrl,
                        speaker: data.user || 'Soundboard',
                        text: `(${data.sound_name})`,
                        voice: 'Soundboard',
                        is_soundboard: true
                    });
                    checkAndPlayNext();
                }
            } catch (err) {
                console.error('OBS Overlay soundboard trigger error:', err);
            }
        });
    }

    let currentFartBgAudio = null;

    // Chaos Mode Playback Handler for OBS Overlay
    function playChaosAudio(item) {
        silentUnlock();
        playChimeSound();
        renderSpectrum();

        const chaosAudio = new Audio(item.url);
        if (audioPlayer && audioPlayer.volume !== undefined) {
            chaosAudio.volume = audioPlayer.volume;
        }
        chaosAudio.play().catch((err) => console.warn('OBS chaos playback note:', err));

        if (obsSpeaker) obsSpeaker.textContent = `🔥 ${item.user || 'Chatter'}`;
        if (obsText) obsText.textContent = item.text || '';

        overlayCard.classList.remove('idle');
        overlayCard.classList.add('speaking');

        if (item.has_fart_bg) {
            try {
                const fartUrl = item.fart_bg_url || '/api/soundboard/fartbackground';
                const fartAudio = new Audio(fartUrl);
                fartAudio.volume = (audioPlayer && audioPlayer.volume !== undefined) ? audioPlayer.volume : 1.0;
                fartAudio.play().catch(() => {});
            } catch (err) {}
        }
    }

    function flushChaosQueue() {
        while (audioQueue.length > 0) {
            const item = audioQueue.shift();
            playChaosAudio(item);
        }
    }

    // Sequential Audio Playback
    function checkAndPlayNext() {
        if (isPlaying || audioQueue.length === 0) return;

        currentItem = audioQueue.shift();
        isPlaying = true;

        silentUnlock();
        playChimeSound();
        renderSpectrum();

        // Update Overlay UI (Essential Username & Text only)
        if (obsSpeaker) obsSpeaker.textContent = currentItem.user || 'Chatter';
        if (obsText) obsText.textContent = currentItem.text || '';

        overlayCard.classList.remove('idle');
        overlayCard.classList.add('speaking');

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
                    console.warn('OBS Overlay fart background audio playback note:', err);
                });
            } catch (err) {
                console.error('Failed to initialize OBS fart background audio:', err);
            }
        }

        // Play Main Audio
        audioPlayer.src = currentItem.url;
        audioPlayer.play().catch((err) => {
            console.warn('OBS Overlay playback note:', err);
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

        overlayCard.classList.remove('speaking');
        overlayCard.classList.add('idle');

        if (audioQueue.length > 0) {
            setTimeout(checkAndPlayNext, 180);
        } else {
            if (obsSpeaker) obsSpeaker.textContent = 'Waiting for TTS...';
            if (obsText) obsText.textContent = 'Twitch TTS Voice Overlay ready.';
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
        console.error('OBS Overlay player audio error:', e);
        onAudioEnded();
    });

    initSSE();
});
