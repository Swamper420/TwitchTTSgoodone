document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const audioPlayer = document.getElementById('audioPlayer');
    const statusPill = document.getElementById('statusPill');
    const statusText = document.getElementById('statusText');
    const channelInput = document.getElementById('channelInput');
    const connectBtn = document.getElementById('connectBtn');

    const queueBadge = document.getElementById('queueBadge');
    const visualizer = document.getElementById('visualizer');
    const speakerName = document.getElementById('currentSpeaker');
    const spokenText = document.getElementById('currentText');
    const voiceTag = document.getElementById('voiceTag');
    const chunkTag = document.getElementById('chunkTag');

    const skipBtn = document.getElementById('skipBtn');
    const clearBtn = document.getElementById('clearBtn');
    const muteBtn = document.getElementById('muteBtn');
    const volumeSlider = document.getElementById('volumeSlider');
    const volumeValue = document.getElementById('volumeValue');
    const chimeToggle = document.getElementById('chimeToggle');
    const autoPlayToggle = document.getElementById('autoPlayToggle');

    const queueList = document.getElementById('queueList');

    const testTextInput = document.getElementById('testTextInput');
    const testVoiceInput = document.getElementById('testVoiceInput');
    const testModelInput = document.getElementById('testModelInput');
    const sendTestBtn = document.getElementById('sendTestBtn');
    const voiceChips = document.getElementById('voiceChips');

    const apiUrlInput = document.getElementById('apiUrlInput');
    const defaultVoiceInput = document.getElementById('defaultVoiceInput');
    const defaultModelInput = document.getElementById('defaultModelInput');
    const languageInput = document.getElementById('languageInput');
    const speedInput = document.getElementById('speedInput');
    const numStepInput = document.getElementById('numStepInput');
    const guidanceScaleInput = document.getElementById('guidanceScaleInput');
    const seedInput = document.getElementById('seedInput');
    const userTemplateInput = document.getElementById('userTemplateInput');
    const sameUserTimeoutInput = document.getElementById('sameUserTimeoutInput');
    const voicePresetsInput = document.getElementById('voicePresetsInput');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');

    const chatFeed = document.getElementById('chatFeed');
    const audioUnlockOverlay = document.getElementById('audioUnlockOverlay');
    const enableAudioBtn = document.getElementById('enableAudioBtn');
    const toastContainer = document.getElementById('toastContainer');
    const spectrumCanvas = document.getElementById('spectrumCanvas');
    const canvasCtx = spectrumCanvas ? spectrumCanvas.getContext('2d') : null;

    const userVoicesList = document.getElementById('userVoicesList');
    const clearAllVoicesBtn = document.getElementById('clearAllVoicesBtn');

    // DarkCounter / Kill Counter DOM Elements
    const enableKillCounterToggle = document.getElementById('enableKillCounterToggle');
    const killCounterFileInput = document.getElementById('killCounterFileInput');
    const killCounterVoiceInput = document.getElementById('killCounterVoiceInput');
    const killCounterPollIntervalInput = document.getElementById('killCounterPollIntervalInput');
    const killCounterTemplateInput = document.getElementById('killCounterTemplateInput');
    const currentKillCountDisplay = document.getElementById('currentKillCountDisplay');
    const lastBibleVerseText = document.getElementById('lastBibleVerseText');
    const incrementKillCountBtn = document.getElementById('incrementKillCountBtn');
    const resetKillCountBtn = document.getElementById('resetKillCountBtn');
    const triggerBibleTestBtn = document.getElementById('triggerBibleTestBtn');

    // Constants
    const SILENT_WAV_SRC = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==';

    // Audio Queue State
    let audioQueue = [];
    let isPlaying = false;
    let currentItem = null;
    let bufferTimer = null;

    // Web Audio API State
    let audioCtx = null;
    let analyser = null;
    let audioSource = null;
    let animFrameId = null;

    // Initialize audio player as muted by default on the main page
    if (audioPlayer) {
        audioPlayer.muted = true;
    }
    if (muteBtn) {
        muteBtn.textContent = '🔇';
    }

    // Load initial settings & status
    fetchStatus();

    // Connect Server-Sent Events (SSE)
    initSSE();

    // ----------------------------------------------------
    // Audio Autoplay & Web Audio Visualizer
    // ----------------------------------------------------

    function initWebAudioVisualizer() {
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
            console.log('Web Audio API initialized on user interaction:', e);
        }
    }

    function unlockAudio() {
        initWebAudioVisualizer();
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        if (audioUnlockOverlay) {
            audioUnlockOverlay.classList.add('hidden');
        }
        // Silent play to unlock HTML5 audio element safely without src error
        if (!audioPlayer.src || audioPlayer.src === window.location.href || audioPlayer.src.startsWith('data:')) {
            audioPlayer.src = SILENT_WAV_SRC;
            audioPlayer.play().then(() => {
                audioPlayer.pause();
            }).catch(() => {});
        }

        // Trigger queue playback if items arrived before user interaction
        if (!isPlaying && audioQueue.length > 0) {
            checkAndPlayNext();
        }
    }

    if (enableAudioBtn) {
        enableAudioBtn.addEventListener('click', unlockAudio);
    }
    document.addEventListener('click', unlockAudio, { once: true });

    function playChimeSound() {
        if (!chimeToggle || !chimeToggle.checked) return Promise.resolve();
        return new Promise((resolve) => {
            try {
                const ctx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
                if (ctx.state === 'suspended') {
                    ctx.resume();
                }
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
                osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12); // A5
                gain.gain.setValueAtTime(0.15, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.25);
                setTimeout(resolve, 250);
            } catch (e) {
                resolve();
            }
        });
    }

    function renderSpectrum() {
        if (!canvasCtx || !analyser) return;
        animFrameId = requestAnimationFrame(renderSpectrum);
        
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteFrequencyData(dataArray);

        const width = spectrumCanvas.width;
        const height = spectrumCanvas.height;
        canvasCtx.clearRect(0, 0, width, height);

        const numBars = 20;
        const barGap = 3;
        const step = Math.max(1, Math.floor(bufferLength / numBars));
        const barWidth = Math.max(4, Math.floor((width - (numBars * barGap)) / numBars));

        const blockHeight = 4;
        const blockGap = 2;
        const maxBlocks = Math.floor(height / (blockHeight + blockGap));

        let x = 0;

        for (let i = 0; i < numBars; i++) {
            let sum = 0;
            for (let j = 0; j < step; j++) {
                sum += dataArray[i * step + j] || 0;
            }
            const val = isPlaying ? (sum / step) : 0;
            const ratio = val / 255;
            const activeBlocks = Math.round(ratio * maxBlocks);

            for (let b = 0; b < maxBlocks; b++) {
                const blockY = height - ((b + 1) * (blockHeight + blockGap));

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

    // ----------------------------------------------------
    // Audio Queue Player & Controls
    // ----------------------------------------------------

    function enqueueAudioChunk(chunk) {
        audioQueue.push(chunk);
        updateQueueUI();
        checkAndPlayNext();
    }

    function checkAndPlayNext() {
        if (!autoPlayToggle.checked || isPlaying || audioQueue.length === 0) {
            return;
        }

        const head = audioQueue[0];

        // If this is chunk 1 of a multi-chunk message, wait for chunk 2 to be ready before playing chunk 1
        if (head.total_chunks > 1 && head.chunk_index === 1) {
            const hasChunk2 = audioQueue.some(item => item.chunk_index === 2 && item.user === head.user);
            if (!hasChunk2) {
                if (!bufferTimer) {
                    bufferTimer = setTimeout(() => {
                        bufferTimer = null;
                        if (!isPlaying && audioQueue.length > 0) {
                            playNextChunk();
                        }
                    }, 12000); // Safety fallback timeout if chunk 2 generation fails
                }
                return;
            }
        }

        if (bufferTimer) {
            clearTimeout(bufferTimer);
            bufferTimer = null;
        }

        playNextChunk();
    }

    let currentFartBgAudio = null;

    function stopFartBgAudio() {
        if (currentFartBgAudio) {
            try {
                currentFartBgAudio.pause();
                currentFartBgAudio.currentTime = 0;
            } catch (e) {}
            currentFartBgAudio = null;
        }
    }

    async function playNextChunk() {
        if (bufferTimer) {
            clearTimeout(bufferTimer);
            bufferTimer = null;
        }

        if (audioQueue.length === 0) {
            isPlaying = false;
            currentItem = null;
            stopFartBgAudio();
            if (visualizer) visualizer.classList.remove('playing');
            updateNowPlayingUI(null);
            updateQueueUI();
            return;
        }

        initWebAudioVisualizer();
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume();
        }

        isPlaying = true;
        currentItem = audioQueue.shift();
        if (visualizer) visualizer.classList.add('playing');
        
        updateQueueUI();
        updateNowPlayingUI(currentItem);

        if (currentItem.chunk_index === 1 && chimeToggle && chimeToggle.checked) {
            await playChimeSound();
        }

        // Parallel Fart Background Audio Playback
        if (currentItem && currentItem.has_fart_bg) {
            try {
                stopFartBgAudio();
                const fartUrl = currentItem.fart_bg_url || '/api/soundboard/fartbackground';
                currentFartBgAudio = new Audio(fartUrl);
                if (volumeSlider) {
                    currentFartBgAudio.volume = volumeSlider.value / 100;
                }
                currentFartBgAudio.play().catch((err) => {
                    console.warn('Dashboard fart background audio playback note:', err);
                });
            } catch (err) {
                console.error('Failed to initialize dashboard fart background audio:', err);
            }
        }

        audioPlayer.src = currentItem.url;
        audioPlayer.volume = volumeSlider.value / 100;
        audioPlayer.load();
        
        audioPlayer.play().then(() => {
            if (audioUnlockOverlay) {
                audioUnlockOverlay.classList.add('hidden');
            }
        }).catch(err => {
            console.error('Audio playback error / Autoplay blocked:', err);
            if (visualizer) visualizer.classList.remove('playing');
            stopFartBgAudio();
            
            // Re-queue item so it isn't lost if autoplay was blocked
            if (currentItem) {
                audioQueue.unshift(currentItem);
            }
            isPlaying = false;
            currentItem = null;
            updateNowPlayingUI(null);
            updateQueueUI();

            // Prompt user to activate audio if autoplay was blocked
            if (audioUnlockOverlay) {
                audioUnlockOverlay.classList.remove('hidden');
            }
        });
    }

    // Skip current audio track
    skipBtn.addEventListener('click', async () => {
        try {
            fetch('/api/queue/skip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user: 'Dashboard' })
            }).catch(err => console.warn('Skip API note:', err));
        } catch (e) {}

        stopFartBgAudio();
        if (isPlaying || currentItem) {
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
            if (visualizer) visualizer.classList.remove('playing');
            isPlaying = false;
            currentItem = null;
            showToast('Skipped current audio', 'success');
            checkAndPlayNext();
        }
    });

    // Clear entire queue
    clearBtn.addEventListener('click', () => {
        if (bufferTimer) {
            clearTimeout(bufferTimer);
            bufferTimer = null;
        }
        stopFartBgAudio();
        audioQueue = [];
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
        isPlaying = false;
        currentItem = null;
        if (visualizer) visualizer.classList.remove('playing');
        updateNowPlayingUI(null);
        updateQueueUI();
        showToast('Cleared audio queue', 'success');
    });

    // Volume & Mute Controls
    if (volumeSlider) {
        volumeSlider.addEventListener('input', () => {
            const val = parseInt(volumeSlider.value, 10);
            if (audioPlayer) {
                audioPlayer.volume = val / 100;
            }
            if (volumeValue) {
                volumeValue.textContent = `${val}%`;
            }
            if (val === 0) {
                if (audioPlayer) audioPlayer.muted = true;
                if (muteBtn) muteBtn.textContent = '🔇';
            } else {
                // If user turns volume up, unmute automatically
                if (audioPlayer) audioPlayer.muted = false;
                if (muteBtn) muteBtn.textContent = '🔊';
            }
        });
    }

    if (muteBtn) {
        muteBtn.addEventListener('click', () => {
            if (!audioPlayer) return;
            audioPlayer.muted = !audioPlayer.muted;
            muteBtn.textContent = audioPlayer.muted ? '🔇' : '🔊';
        });
    }

    audioPlayer.addEventListener('ended', () => {
        if (visualizer) visualizer.classList.remove('playing');
        isPlaying = false;
        if (autoPlayToggle.checked) {
            checkAndPlayNext();
        }
    });

    audioPlayer.addEventListener('error', (e) => {
        if (audioPlayer.src === SILENT_WAV_SRC || !audioPlayer.src || audioPlayer.src === window.location.href) {
            return;
        }
        console.error('Playback error on track:', e);
        if (visualizer) visualizer.classList.remove('playing');
        isPlaying = false;
        if (currentItem) {
            currentItem = null;
            updateNowPlayingUI(null);
        }
        checkAndPlayNext();
    });

    // Global Hotkeys
    document.addEventListener('keydown', (e) => {
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
            return;
        }

        if (e.code === 'Space') {
            e.preventDefault();
            if (audioPlayer.paused && currentItem) {
                audioPlayer.play();
                if (visualizer) visualizer.classList.add('playing');
            } else {
                audioPlayer.pause();
                if (visualizer) visualizer.classList.remove('playing');
            }
        } else if (e.code === 'KeyS') {
            skipBtn.click();
        } else if (e.code === 'KeyC') {
            clearBtn.click();
        } else if (e.code === 'KeyM') {
            muteBtn.click();
        }
    });

    function updateQueueUI() {
        queueBadge.textContent = `${audioQueue.length} in queue`;

        if (!queueList) return;
        queueList.innerHTML = '';

        if (audioQueue.length === 0) {
            queueList.innerHTML = '<div class="queue-empty-text">Queue is currently empty</div>';
            return;
        }

        audioQueue.forEach((item, idx) => {
            const div = document.createElement('div');
            div.className = 'queue-item';
            div.innerHTML = `
                <div class="queue-item-info">
                    <span class="queue-item-user">#${idx + 1} - ${escapeHtml(item.user)} (${escapeHtml(item.voice || 'default')})</span>
                    <span class="queue-item-text">"${escapeHtml(item.text)}"</span>
                </div>
                <button class="queue-item-remove" title="Remove from queue" data-index="${idx}">✖</button>
            `;
            queueList.appendChild(div);
        });

        // Add event listeners to remove buttons
        queueList.querySelectorAll('.queue-item-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-index'), 10);
                if (!isNaN(idx) && idx >= 0 && idx < audioQueue.length) {
                    audioQueue.splice(idx, 1);
                    updateQueueUI();
                    showToast('Removed item from queue', 'success');
                }
            });
        });
    }

    function updateNowPlayingUI(item) {
        if (!item) {
            speakerName.textContent = 'Idle / Ready';
            spokenText.textContent = 'Waiting for Twitch chat messages or manual test input...';
            voiceTag.textContent = 'Voice: Default';
            chunkTag.textContent = 'Chunk: 0 / 0';
            return;
        }

        speakerName.textContent = item.user;
        spokenText.textContent = `"${item.text}"`;
        voiceTag.textContent = `Voice: ${item.voice || 'default'}${item.has_8d ? ' (8D)' : ''}`;
        chunkTag.textContent = `Chunk: ${item.chunk_index} / ${item.total_chunks}`;
    }

    // ----------------------------------------------------
    // Voice Tag Chips Helper
    // ----------------------------------------------------

    if (voiceChips) {
        voiceChips.addEventListener('click', (e) => {
            if (e.target.classList.contains('chip')) {
                const voice = e.target.getAttribute('data-voice');
                const tag = e.target.getAttribute('data-tag');
                if (voice) {
                    testTextInput.value = (testTextInput.value + ` [${voice}] `).trimStart();
                    testTextInput.focus();
                } else if (tag) {
                    testTextInput.value = (testTextInput.value + ` ${tag} `).trimStart();
                    testTextInput.focus();
                }
            }
        });
    }

    // ----------------------------------------------------
    // Server-Sent Events (SSE)
    // ----------------------------------------------------

    function initSSE() {
        const evtSource = new EventSource('/api/events');

        evtSource.addEventListener('status', (e) => {
            const data = JSON.parse(e.data);
            updateStatusUI(data);
        });

        evtSource.addEventListener('audio_chunk', (e) => {
            const chunk = JSON.parse(e.data);
            enqueueAudioChunk(chunk);
        });

        evtSource.addEventListener('chat_message', (e) => {
            const data = JSON.parse(e.data);
            addChatMessage(data.user, data.message);
        });

        evtSource.addEventListener('counter_update', (e) => {
            const counterData = JSON.parse(e.data);
            updateCounterUI(counterData);
        });

        evtSource.addEventListener('skip_audio', () => {
            if (isPlaying || currentItem) {
                audioPlayer.pause();
                audioPlayer.currentTime = 0;
                if (visualizer) visualizer.classList.remove('playing');
                isPlaying = false;
                currentItem = null;
                showToast('Skipped current audio', 'info');
                checkAndPlayNext();
            }
        });

        evtSource.addEventListener('clear_audio', () => {
            if (bufferTimer) {
                clearTimeout(bufferTimer);
                bufferTimer = null;
            }
            audioQueue = [];
            if (isPlaying || currentItem) {
                audioPlayer.pause();
                audioPlayer.currentTime = 0;
                if (visualizer) visualizer.classList.remove('playing');
                isPlaying = false;
                currentItem = null;
            }
            updateQueueUI();
            showToast('Cleared audio queue', 'info');
        });

        evtSource.addEventListener('error', (e) => {
            if (bufferTimer) {
                clearTimeout(bufferTimer);
                bufferTimer = null;
            }
            if (!isPlaying && audioQueue.length > 0) {
                checkAndPlayNext();
            }
            if (e.data) {
                try {
                    const errData = JSON.parse(e.data);
                    console.error('Server SSE error:', errData.message);
                    showToast(`Error: ${errData.message}`, 'error');
                } catch(err){}
            }
        });
    }

    // ----------------------------------------------------
    // API Actions & Forms
    // ----------------------------------------------------

    function getAuthHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const adminToken = localStorage.getItem('admin_token');
        if (adminToken) {
            headers['X-Admin-Token'] = adminToken;
        }
        return headers;
    }

    async function handleFetchResponse(res) {
        if (res.status === 401) {
            const data = await res.json().catch(() => ({}));
            if (data.auth_required) {
                showAdminLoginModal();
            }
            return null;
        }
        return res;
    }

    function showAdminLoginModal() {
        const modal = document.getElementById('adminLoginModal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    }

    function hideAdminLoginModal() {
        const modal = document.getElementById('adminLoginModal');
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    async function fetchStatus() {
        try {
            const res = await fetch('/api/status', { headers: getAuthHeaders() });
            const validRes = await handleFetchResponse(res);
            if (validRes && validRes.ok) {
                const data = await validRes.json();
                updateStatusUI(data);
            }
        } catch (e) {
            console.error('Failed to fetch status:', e);
        }
    }

    function updateStatusUI(data) {
        const authBadge = document.getElementById('authBadge');
        const authText = document.getElementById('authText');
        const botUsernameInput = document.getElementById('botUsernameInput');
        const botOauthInput = document.getElementById('botOauthInput');
        const adminPasswordInput = document.getElementById('adminPasswordInput');
        const enableChatResponsesToggle = document.getElementById('enableChatResponsesToggle');
        const enablePeriodicInfoToggle = document.getElementById('enablePeriodicInfoToggle');
        const periodicInfoIntervalInput = document.getElementById('periodicInfoIntervalInput');

        if (data.channel) {
            channelInput.value = data.channel;
        }
        if (data.connected && (data.channels ? data.channels.length > 0 : data.channel)) {
            statusPill.classList.add('connected');
            const chList = data.channels && data.channels.length > 0 ? data.channels.map(c => '#' + c).join(', ') : `#${data.channel}`;
            statusText.textContent = `Connected: ${chList}`;
            connectBtn.textContent = 'Disconnect';
        } else {
            statusPill.classList.remove('connected');
            statusText.textContent = 'Disconnected';
            connectBtn.textContent = 'Connect';
        }

        // Update OBS Overlay links display (uses public server port or configured site domain)
        const publicPort = data.config && (data.config.public_server_port || data.config.obs_server_port) ? (data.config.public_server_port || data.config.obs_server_port) : 5001;
        const siteDomain = data.config && (data.config.site_domain || data.config.public_domain || data.config.domain) ? String(data.config.site_domain || data.config.public_domain || data.config.domain).trim() : '';

        let publicBaseUrl;
        if (siteDomain) {
            let cleanDomain = siteDomain.replace(/\/+$/, '');
            if (cleanDomain.startsWith('http://') || cleanDomain.startsWith('https://')) {
                publicBaseUrl = cleanDomain;
            } else if (cleanDomain.includes(':')) {
                publicBaseUrl = `http://${cleanDomain}`;
            } else if (publicPort && publicPort !== 80 && publicPort !== 443) {
                publicBaseUrl = `http://${cleanDomain}:${publicPort}`;
            } else {
                publicBaseUrl = `http://${cleanDomain}`;
            }
        } else {
            const host = window.location.hostname || 'localhost';
            publicBaseUrl = `http://${host}:${publicPort}`;
        }
        const obsBaseUrl = `${publicBaseUrl}/obs`;

        // Update navbar links to point to the public server
        const publicPlayerLink = document.getElementById('publicPlayerLink');
        if (publicPlayerLink) publicPlayerLink.href = `${publicBaseUrl}/player`;
        const publicObsLink = document.getElementById('publicObsLink');
        if (publicObsLink) publicObsLink.href = `${publicBaseUrl}/obs`;

        const obsLinkAll = document.getElementById('obsLinkAll');
        if (obsLinkAll) obsLinkAll.value = obsBaseUrl;

        const chan1Label = document.getElementById('chan1Label');
        const chan2Label = document.getElementById('chan2Label');
        const obsLinkChan1 = document.getElementById('obsLinkChan1');
        const obsLinkChan2 = document.getElementById('obsLinkChan2');

        const channels = data.channels && data.channels.length > 0 ? data.channels : (data.channel ? [data.channel] : []);

        if (chan1Label) chan1Label.textContent = channels[0] ? `#${channels[0]}` : 'None';
        if (obsLinkChan1) obsLinkChan1.value = channels[0] ? `${obsBaseUrl}?channel=${encodeURIComponent(channels[0])}` : `${obsBaseUrl}?channel=`;

        if (chan2Label) chan2Label.textContent = channels[1] ? `#${channels[1]}` : 'None';
        if (obsLinkChan2) obsLinkChan2.value = channels[1] ? `${obsBaseUrl}?channel=${encodeURIComponent(channels[1])}` : `${obsBaseUrl}?channel=`;

        if (authBadge && authText) {
            if (data.authenticated) {
                authBadge.classList.add('authenticated');
                const botName = data.config && data.config.twitch_bot_username ? data.config.twitch_bot_username : (data.twitch_auth && data.twitch_auth.login ? data.twitch_auth.login : 'Bot');
                authText.textContent = `Bot Active (@${botName})`;
            } else {
                authBadge.classList.remove('authenticated');
                authText.textContent = 'Read-Only (justinfan)';
            }
        }

        if (data.twitch_auth) {
            updateTwitchAuthBadgeUI(data.twitch_auth);
        }

        if (data.config) {
            if (apiUrlInput) apiUrlInput.value = data.config.tts_api_url || '';
            if (defaultVoiceInput) defaultVoiceInput.value = data.config.tts_voice || '';
            if (defaultModelInput) defaultModelInput.value = data.config.tts_model || '';
            if (formatSelect) formatSelect.value = data.config.tts_format || 'wav';
            if (languageInput) languageInput.value = data.config.tts_language || 'fi';
            if (speedInput) speedInput.value = data.config.tts_speed !== undefined ? data.config.tts_speed : 1.0;
            if (numStepInput) numStepInput.value = data.config.tts_num_step !== undefined ? data.config.tts_num_step : 32;
            if (guidanceScaleInput) guidanceScaleInput.value = data.config.tts_guidance_scale !== undefined ? data.config.tts_guidance_scale : 2.0;
            if (seedInput) seedInput.value = data.config.tts_seed !== undefined ? data.config.tts_seed : 42;
            if (userTemplateInput) userTemplateInput.value = data.config.user_template || '';
            if (sameUserTimeoutInput) sameUserTimeoutInput.value = data.config.same_user_timeout !== undefined ? data.config.same_user_timeout : 10;
            if (voicePresetsInput) voicePresetsInput.value = data.config.voice_presets || '';
            const effect8dSpeedInput = document.getElementById('effect8dSpeedInput');
            if (effect8dSpeedInput) effect8dSpeedInput.value = data.config.effect_8d_speed !== undefined ? data.config.effect_8d_speed : 0.15;

            if (botUsernameInput) botUsernameInput.value = data.config.twitch_bot_username || '';
            if (botOauthInput && data.config.twitch_oauth_token) {
                botOauthInput.value = data.config.twitch_oauth_token;
            }
            if (adminPasswordInput && data.config.admin_password) {
                adminPasswordInput.value = data.config.admin_password;
            }
            if (enableChatResponsesToggle) enableChatResponsesToggle.checked = data.config.enable_chat_responses !== false;
            if (enablePeriodicInfoToggle) enablePeriodicInfoToggle.checked = !!data.config.enable_periodic_info;
            if (periodicInfoIntervalInput) periodicInfoIntervalInput.value = data.config.periodic_info_interval || 15;

            renderVoiceChips(data.config.voice_presets);
        }

        if (data.user_voices) {
            renderUserVoices(data.user_voices);
        }

        if (data.counter) {
            updateCounterUI(data.counter);
        }
    }

    function updateCounterUI(counterData) {
        if (!counterData) return;
        if (currentKillCountDisplay) {
            currentKillCountDisplay.textContent = counterData.count !== undefined ? counterData.count : 0;
        }
        if (lastBibleVerseText) {
            if (counterData.last_verse && counterData.last_verse.reference) {
                lastBibleVerseText.textContent = `${counterData.last_verse.reference}: "${counterData.last_verse.text}"`;
            } else {
                lastBibleVerseText.textContent = 'None yet';
            }
        }
        if (enableKillCounterToggle && document.activeElement !== enableKillCounterToggle) {
            enableKillCounterToggle.checked = !!counterData.enabled;
        }
        if (killCounterFileInput && document.activeElement !== killCounterFileInput) {
            killCounterFileInput.value = counterData.file || 'values/deaths';
        }
        if (killCounterVoiceInput && document.activeElement !== killCounterVoiceInput) {
            killCounterVoiceInput.value = counterData.voice || 'terapisti';
        }
        if (killCounterTemplateInput && document.activeElement !== killCounterTemplateInput) {
            killCounterTemplateInput.value = counterData.template || '';
        }
    }

    function renderVoiceChips(voicePresetsStr) {
        if (!voiceChips || !voicePresetsStr) return;
        const voices = voicePresetsStr.split(',').map(v => v.trim()).filter(v => v.length > 0);
        voiceChips.innerHTML = '';
        voices.forEach(voice => {
            const chip = document.createElement('span');
            chip.className = 'chip';
            chip.setAttribute('data-voice', voice);
            chip.textContent = `+ [${voice}]`;
            voiceChips.appendChild(chip);
        });
    }

    function renderUserVoices(userVoicesObj) {
        if (!userVoicesList) return;
        userVoicesList.innerHTML = '';
        const entries = Object.entries(userVoicesObj || {});
        if (entries.length === 0) {
            userVoicesList.innerHTML = '<span class="user-voices-empty">No chatter voices claimed yet. Type <code>!myvoice &lt;name&gt;</code> in chat!</span>';
            return;
        }

        entries.forEach(([user, voice]) => {
            const tag = document.createElement('span');
            tag.className = 'user-voice-tag';
            tag.innerHTML = `
                <span class="name">@${escapeHtml(user)}</span>:
                <span class="voice">${escapeHtml(voice)}</span>
                <button class="remove-btn" data-user="${escapeHtml(user)}" title="Reset voice for @${escapeHtml(user)}">✖</button>
            `;
            userVoicesList.appendChild(tag);
        });

        userVoicesList.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const username = e.currentTarget.getAttribute('data-user');
                if (username) {
                    await deleteUserVoice(username);
                }
            });
        });
    }

    async function deleteUserVoice(username) {
        try {
            const res = await fetch('/api/user_voices/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user: username })
            });
            if (res.ok) {
                showToast(`Reset voice for @${username}`, 'success');
                fetchStatus();
            }
        } catch(e) {
            console.error('Failed to delete user voice:', e);
        }
    }

    if (clearAllVoicesBtn) {
        clearAllVoicesBtn.addEventListener('click', async () => {
            if (confirm('Clear all saved chatter voices?')) {
                try {
                    const res = await fetch('/api/user_voices/clear', { method: 'POST' });
                    if (res.ok) {
                        showToast('Cleared all saved chatter voices', 'success');
                        fetchStatus();
                    }
                } catch(e) {
                    console.error('Failed to clear user voices:', e);
                }
            }
        });
    }

    function updateTwitchAuthBadgeUI(info) {
        const badge = document.getElementById('twitchOAuthBadge');
        const drawer = document.getElementById('twitchAuthDetails');
        const loginEl = document.getElementById('authDetailLogin');
        const userIdEl = document.getElementById('authDetailUserId');
        const clientIdEl = document.getElementById('authDetailClientId');
        const expiresEl = document.getElementById('authDetailExpires');
        const scopesEl = document.getElementById('authDetailScopes');

        if (!badge) return;

        if (!info || !info.valid) {
            if (info && info.error && info.error !== 'No OAuth token provided') {
                badge.className = 'auth-status-badge badge-invalid';
                badge.innerHTML = `<span class="badge-icon">❌</span><span class="badge-label">Invalid OAuth Token (${escapeHtml(info.error)})</span>`;
            } else {
                badge.className = 'auth-status-badge badge-anon';
                badge.innerHTML = `<span class="badge-icon">⚠️</span><span class="badge-label">Anonymous Reader Mode (justinfan)</span>`;
            }
            if (drawer) drawer.classList.add('hidden');
            return;
        }

        badge.className = 'auth-status-badge badge-valid';
        badge.innerHTML = `<span class="badge-icon">✓</span><span class="badge-label">Validated as @${escapeHtml(info.login)}</span>`;

        if (drawer) {
            drawer.classList.remove('hidden');
            if (loginEl) loginEl.textContent = `@${info.login}`;
            if (userIdEl) userIdEl.textContent = info.user_id || 'N/A';
            if (clientIdEl) clientIdEl.textContent = info.client_id ? `${info.client_id.substring(0, 8)}...` : 'N/A';
            
            if (expiresEl) {
                const mins = Math.floor((info.expires_in || 0) / 60);
                const hrs = Math.floor(mins / 60);
                if (hrs > 24) {
                    expiresEl.textContent = `${Math.floor(hrs / 24)} days`;
                } else if (hrs > 0) {
                    expiresEl.textContent = `${hrs} hrs ${mins % 60} mins`;
                } else {
                    expiresEl.textContent = `${mins} mins`;
                }
            }

            if (scopesEl && Array.isArray(info.scopes)) {
                if (info.scopes.length === 0) {
                    scopesEl.innerHTML = '<span class="scope-tag">no scopes</span>';
                } else {
                    scopesEl.innerHTML = info.scopes.map(s => {
                        const isRead = s.includes('read');
                        const isEdit = s.includes('edit');
                        const cls = isRead ? 'scope-read' : (isEdit ? 'scope-edit' : '');
                        return `<span class="scope-tag ${cls}">${escapeHtml(s)}</span>`;
                    }).join('');
                }
            }
        }
    }

    async function validateTwitchToken() {
        const botOauthInput = document.getElementById('botOauthInput');
        const botUsernameInput = document.getElementById('botUsernameInput');
        const validateTokenBtn = document.getElementById('validateTokenBtn');

        const token = botOauthInput ? botOauthInput.value.trim() : '';
        if (!token) {
            updateTwitchAuthBadgeUI({ valid: false, error: 'No OAuth token provided' });
            showToast('Please enter a Twitch OAuth token to validate', 'info');
            return;
        }

        if (validateTokenBtn) {
            validateTokenBtn.disabled = true;
            validateTokenBtn.textContent = '⏳ Validating...';
        }

        try {
            const res = await fetch('/api/auth/validate_twitch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ oauth_token: token })
            });

            if (res.ok) {
                const data = await res.json();
                updateTwitchAuthBadgeUI(data);
                if (data.valid) {
                    showToast(`Twitch Token Valid! Authenticated as @${data.login}`, 'success');
                    if (botUsernameInput && (!botUsernameInput.value.trim() || botUsernameInput.value === 'my_tts_bot')) {
                        botUsernameInput.value = data.login;
                        showToast(`Auto-detected bot username: @${data.login}`, 'info');
                    }
                } else {
                    showToast(`Validation Failed: ${data.error || 'Invalid token'}`, 'error');
                }
            } else {
                showToast('Failed to validate token with backend', 'error');
            }
        } catch (e) {
            console.error('Validation error:', e);
            showToast('Error validating token', 'error');
        } finally {
            if (validateTokenBtn) {
                validateTokenBtn.disabled = false;
                validateTokenBtn.textContent = '⚡ Validate Token';
            }
        }
    }

    const validateTokenBtn = document.getElementById('validateTokenBtn');
    if (validateTokenBtn) {
        validateTokenBtn.addEventListener('click', validateTwitchToken);
    }

    const autoDetectBotBtn = document.getElementById('autoDetectBotBtn');
    if (autoDetectBotBtn) {
        autoDetectBotBtn.addEventListener('click', validateTwitchToken);
    }

    const toggleOauthVisibilityBtn = document.getElementById('toggleOauthVisibilityBtn');
    if (toggleOauthVisibilityBtn) {
        toggleOauthVisibilityBtn.addEventListener('click', () => {
            const input = document.getElementById('botOauthInput');
            if (input) {
                input.type = input.type === 'password' ? 'text' : 'password';
            }
        });
    }

    const toggleAdminPasswordVisibilityBtn = document.getElementById('toggleAdminPasswordVisibilityBtn');
    if (toggleAdminPasswordVisibilityBtn) {
        toggleAdminPasswordVisibilityBtn.addEventListener('click', () => {
            const input = document.getElementById('adminPasswordInput');
            if (input) {
                input.type = input.type === 'password' ? 'text' : 'password';
            }
        });
    }

    // Admin Login Modal Handlers
    const loginSubmitBtn = document.getElementById('loginSubmitBtn');
    const loginPasswordInput = document.getElementById('loginPasswordInput');
    const loginErrorMsg = document.getElementById('loginErrorMsg');

    async function performAdminLogin() {
        if (!loginPasswordInput) return;
        const password = loginPasswordInput.value.trim();
        if (loginErrorMsg) loginErrorMsg.classList.add('hidden');

        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.token) {
                    localStorage.setItem('admin_token', data.token);
                    hideAdminLoginModal();
                    showToast('Dashboard Admin Unlocked!', 'success');
                    fetchStatus();
                }
            } else {
                const errData = await res.json().catch(() => ({}));
                if (loginErrorMsg) {
                    loginErrorMsg.textContent = errData.error || 'Invalid Admin Password';
                    loginErrorMsg.classList.remove('hidden');
                }
            }
        } catch (e) {
            console.error('Admin login error:', e);
            if (loginErrorMsg) {
                loginErrorMsg.textContent = 'Server connection error';
                loginErrorMsg.classList.remove('hidden');
            }
        }
    }

    if (loginSubmitBtn) {
        loginSubmitBtn.addEventListener('click', performAdminLogin);
    }
    if (loginPasswordInput) {
        loginPasswordInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') performAdminLogin();
        });
    }

    // Connect Channel Button
    connectBtn.addEventListener('click', async () => {
        const targetChannel = channelInput.value.trim();
        if (!targetChannel) {
            showToast('Please enter a channel name', 'error');
            return;
        }

        try {
            const res = await fetch('/api/connect', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({ channel: targetChannel })
            });
            const validRes = await handleFetchResponse(res);
            if (validRes && validRes.ok) {
                const data = await validRes.json();
                const connStr = data.channels && data.channels.length > 0 ? data.channels.map(c => '#' + c).join(', ') : `#${targetChannel}`;
                showToast(`Connecting to Twitch channel(s) ${connStr}...`, 'success');
                fetchStatus();
            }
        } catch (e) {
            console.error('Failed to connect channel:', e);
            showToast('Failed to connect to Twitch channel', 'error');
        }
    });

    // Save Settings
    saveSettingsBtn.addEventListener('click', async () => {
        const botUsernameInput = document.getElementById('botUsernameInput');
        const botOauthInput = document.getElementById('botOauthInput');
        const adminPasswordInput = document.getElementById('adminPasswordInput');
        const enableChatResponsesToggle = document.getElementById('enableChatResponsesToggle');
        const enablePeriodicInfoToggle = document.getElementById('enablePeriodicInfoToggle');
        const periodicInfoIntervalInput = document.getElementById('periodicInfoIntervalInput');
        const effect8dSpeedInput = document.getElementById('effect8dSpeedInput');

        try {
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    tts_api_url: apiUrlInput ? apiUrlInput.value.trim() : '',
                    tts_voice: defaultVoiceInput ? defaultVoiceInput.value.trim() : '',
                    tts_model: defaultModelInput ? defaultModelInput.value.trim() : '',
                    tts_format: formatSelect ? formatSelect.value : 'wav',
                    tts_language: languageInput ? languageInput.value.trim() : 'fi',
                    tts_speed: speedInput ? (parseFloat(speedInput.value) || 1.0) : 1.0,
                    tts_num_step: numStepInput ? (parseInt(numStepInput.value, 10) || 32) : 32,
                    tts_guidance_scale: guidanceScaleInput ? (parseFloat(guidanceScaleInput.value) || 2.0) : 2.0,
                    tts_seed: seedInput ? (parseInt(seedInput.value, 10) || 42) : 42,
                    user_template: userTemplateInput ? userTemplateInput.value.trim() : '',
                    voice_presets: voicePresetsInput ? voicePresetsInput.value.trim() : '',
                    effect_8d_speed: effect8dSpeedInput ? (parseFloat(effect8dSpeedInput.value) || 0.15) : 0.15,
                    twitch_bot_username: botUsernameInput ? botUsernameInput.value.trim() : '',
                    twitch_oauth_token: botOauthInput ? botOauthInput.value.trim() : '',
                    admin_password: adminPasswordInput ? adminPasswordInput.value.trim() : '',
                    enable_chat_responses: enableChatResponsesToggle ? enableChatResponsesToggle.checked : true,
                    enable_periodic_info: enablePeriodicInfoToggle ? enablePeriodicInfoToggle.checked : false,
                    periodic_info_interval: periodicInfoIntervalInput ? (parseInt(periodicInfoIntervalInput.value, 10) || 15) : 15,
                    same_user_timeout: sameUserTimeoutInput ? (parseFloat(sameUserTimeoutInput.value) >= 0 ? parseFloat(sameUserTimeoutInput.value) : 10) : 10,
                    enable_kill_counter: enableKillCounterToggle ? enableKillCounterToggle.checked : true,
                    kill_counter_file: killCounterFileInput ? killCounterFileInput.value.trim() : 'values/deaths',
                    kill_counter_voice: killCounterVoiceInput ? killCounterVoiceInput.value.trim() : 'terapisti',
                    kill_counter_poll_interval: killCounterPollIntervalInput ? (parseFloat(killCounterPollIntervalInput.value) || 1.0) : 1.0,
                    kill_counter_template: killCounterTemplateInput ? killCounterTemplateInput.value.trim() : ''
                })
            });
            const validRes = await handleFetchResponse(res);
            if (validRes && validRes.ok) {
                showToast('Settings saved persistently!', 'success');
                fetchStatus();
            } else if (validRes) {
                showToast('Failed to save settings', 'error');
            }
        } catch (e) {
            console.error('Failed to save settings:', e);
            showToast('Failed to save settings', 'error');
        }
    });

    const sendHelpfulInfoBtn = document.getElementById('sendHelpfulInfoBtn');
    if (sendHelpfulInfoBtn) {
        sendHelpfulInfoBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/bot/send_info', { method: 'POST', headers: getAuthHeaders() });
                const validRes = await handleFetchResponse(res);
                if (validRes && validRes.ok) {
                    showToast('Posted helpful bot info tip to chat!', 'success');
                }
            } catch (e) {
                console.error('Failed to send helpful info:', e);
                showToast('Error connecting to backend', 'error');
            }
        });
    }

    // Kill Counter Action Buttons
    if (incrementKillCountBtn) {
        incrementKillCountBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/counter', {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ increment: 1 })
                });
                const validRes = await handleFetchResponse(res);
                if (validRes && validRes.ok) {
                    const data = await validRes.json();
                    showToast(`Incremented Kill Count to ${data.count}! Triggered Bible TTS.`, 'success');
                }
            } catch (e) {
                console.error('Failed to increment counter:', e);
                showToast('Error incrementing kill counter', 'error');
            }
        });
    }

    if (resetKillCountBtn) {
        resetKillCountBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/counter', {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ count: 0, trigger_tts: false })
                });
                const validRes = await handleFetchResponse(res);
                if (validRes && validRes.ok) {
                    showToast('Reset kill count to 0.', 'success');
                }
            } catch (e) {
                console.error('Failed to reset counter:', e);
                showToast('Error resetting kill counter', 'error');
            }
        });
    }

    if (triggerBibleTestBtn) {
        triggerBibleTestBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/counter/test', {
                    method: 'POST',
                    headers: getAuthHeaders()
                });
                const validRes = await handleFetchResponse(res);
                if (validRes && validRes.ok) {
                    const data = await validRes.json();
                    const ref = data.verse ? data.verse.reference : '';
                    showToast(`Triggered Bible Quote TTS (${ref})!`, 'success');
                }
            } catch (e) {
                console.error('Failed to trigger Bible quote test:', e);
                showToast('Error triggering Bible quote test', 'error');
            }
        });
    }

    // Copy OBS Overlay Link Event Handler
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('copy-link-btn') || e.target.closest('.copy-link-btn')) {
            const btn = e.target.classList.contains('copy-link-btn') ? e.target : e.target.closest('.copy-link-btn');
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (input && input.value) {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(input.value).then(() => {
                        showToast('OBS Overlay URL copied to clipboard!', 'success');
                    }).catch(() => {
                        input.select();
                        document.execCommand('copy');
                        showToast('OBS Overlay URL copied!', 'success');
                    });
                } else {
                    input.select();
                    document.execCommand('copy');
                    showToast('OBS Overlay URL copied!', 'success');
                }
            }
        }
    });

    // Chat Feed Helper
    function addChatMessage(user, msg) {
        const placeholder = chatFeed.querySelector('.chat-placeholder');
        if (placeholder) placeholder.remove();

        const div = document.createElement('div');
        div.className = 'chat-item';
        div.innerHTML = `<span class="chat-user">${escapeHtml(user)}:</span><span class="chat-msg">${escapeHtml(msg)}</span>`;
        chatFeed.appendChild(div);
        chatFeed.scrollTop = chatFeed.scrollHeight;
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Toast Notification Helper
    function showToast(message, type = 'info') {
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icon = type === 'error' ? '❌' : type === 'success' ? 'SUCCESS' : 'ℹ️';
        toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
});
