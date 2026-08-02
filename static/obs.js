document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const audioPlayer = document.getElementById('obsAudioPlayer');
    const overlayCard = document.getElementById('obsOverlayCard');
    const liveText = document.getElementById('obsLiveText');
    
    const obsSpeaker = document.getElementById('obsSpeaker');
    const obsText = document.getElementById('obsText');
    const obsVoiceTag = document.getElementById('obsVoiceTag');
    const obsChunkTag = document.getElementById('obsChunkTag');
    const obsAvatar = document.getElementById('obsAvatar');
    
    const obsCanvas = document.getElementById('obsCanvas');
    const canvasCtx = obsCanvas ? obsCanvas.getContext('2d') : null;

    // Constants
    const SILENT_WAV = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==';

    // Query Parameters
    const params = new URLSearchParams(window.location.search);
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

            canvasCtx.clearRect(0, 0, obsCanvas.width, obsCanvas.height);

            const barWidth = (obsCanvas.width / bufferLength) * 1.5;
            let barHeight;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                barHeight = (dataArray[i] / 255) * obsCanvas.height;

                const gradient = canvasCtx.createLinearGradient(0, obsCanvas.height, 0, 0);
                gradient.addColorStop(0, 'rgba(145, 70, 255, 0.85)');
                gradient.addColorStop(1, 'rgba(0, 240, 255, 0.95)');

                canvasCtx.fillStyle = gradient;
                canvasCtx.fillRect(x, obsCanvas.height - barHeight, barWidth - 2, barHeight);

                x += barWidth + 1;
            }
        }
        draw();
    }

    // Connect SSE Event Stream
    function initSSE() {
        const evtSource = new EventSource('/api/events');

        evtSource.onopen = () => {
            if (liveText) liveText.textContent = 'LIVE TTS';
        };

        evtSource.onerror = () => {
            if (liveText) liveText.textContent = 'RECONNECTING...';
        };

        evtSource.addEventListener('audio_chunk', (e) => {
            try {
                const item = JSON.parse(e.data);
                if (!item || !item.url) return;
                
                audioQueue.push(item);
                checkAndPlayNext();
            } catch (err) {
                console.error('OBS Overlay audio chunk error:', err);
            }
        });

        evtSource.addEventListener('skip_audio', () => {
            skipCurrentAudio();
        });

        evtSource.addEventListener('clear_audio', () => {
            audioQueue = [];
            skipCurrentAudio();
        });
    }

    // Sequential Audio Playback
    function checkAndPlayNext() {
        if (isPlaying || audioQueue.length === 0) return;

        currentItem = audioQueue.shift();
        isPlaying = true;

        silentUnlock();
        playChimeSound();
        renderSpectrum();

        // Update Overlay UI
        if (obsSpeaker) obsSpeaker.textContent = currentItem.user || 'Chatter';
        if (obsText) obsText.textContent = currentItem.text || '';
        if (obsVoiceTag) obsVoiceTag.textContent = `Voice: ${currentItem.voice || 'Default'}`;
        if (obsChunkTag) obsChunkTag.textContent = `Chunk ${currentItem.chunk_index || 1}/${currentItem.total_chunks || 1}`;

        overlayCard.classList.remove('idle');
        overlayCard.classList.add('speaking');

        // Play Audio
        audioPlayer.src = currentItem.url;
        audioPlayer.play().catch((err) => {
            console.warn('OBS Overlay playback note:', err);
            onAudioEnded();
        });
    }

    function onAudioEnded() {
        isPlaying = false;
        currentItem = null;

        overlayCard.classList.remove('speaking');
        overlayCard.classList.add('idle');

        if (audioQueue.length > 0) {
            setTimeout(checkAndPlayNext, 180);
        } else {
            if (obsSpeaker) obsSpeaker.textContent = 'Waiting for TTS...';
            if (obsText) obsText.textContent = 'Twitch TTS Voice Overlay ready.';
            if (obsChunkTag) obsChunkTag.textContent = 'Ready';
        }
    }

    function skipCurrentAudio() {
        audioPlayer.pause();
        onAudioEnded();
    }

    audioPlayer.addEventListener('ended', onAudioEnded);
    audioPlayer.addEventListener('error', (e) => {
        console.error('OBS Overlay player audio error:', e);
        onAudioEnded();
    });

    initSSE();
});
