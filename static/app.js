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
    const autoPlayToggle = document.getElementById('autoPlayToggle');

    const testTextInput = document.getElementById('testTextInput');
    const testVoiceInput = document.getElementById('testVoiceInput');
    const testModelInput = document.getElementById('testModelInput');
    const sendTestBtn = document.getElementById('sendTestBtn');

    const apiUrlInput = document.getElementById('apiUrlInput');
    const defaultVoiceInput = document.getElementById('defaultVoiceInput');
    const formatSelect = document.getElementById('formatSelect');
    const maxChunkInput = document.getElementById('maxChunkInput');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');

    const chatFeed = document.getElementById('chatFeed');

    // Audio Queue State
    let audioQueue = [];
    let isPlaying = false;
    let currentItem = null;
    let bufferTimer = null;

    // Load initial settings & status
    fetchStatus();

    // Connect Server-Sent Events (SSE)
    initSSE();

    // ----------------------------------------------------
    // Audio Player & Queue Management
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

        // If this is the 1st chunk of a multi-chunk message, wait for the 2nd chunk to arrive first
        if (head.total_chunks > 1 && head.chunk_index === 1) {
            if (audioQueue.length < 2) {
                // Wait for 2nd chunk, but set safety timeout in case 2nd chunk fails/delays
                if (!bufferTimer) {
                    bufferTimer = setTimeout(() => {
                        bufferTimer = null;
                        if (!isPlaying && audioQueue.length > 0) {
                            playNextChunk();
                        }
                    }, 3000);
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

    const chimeToggle = document.getElementById('chimeToggle');
    const spectrumCanvas = document.getElementById('spectrumCanvas');
    let canvasCtx = spectrumCanvas ? spectrumCanvas.getContext('2d') : null;

    // Web Audio API State
    let audioCtx = null;
    let analyser = null;
    let audioSource = null;

    function initWebAudioVisualizer() {
        if (audioCtx) return;
        try {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;
            audioSource = audioCtx.createMediaElementSource(audioPlayer);
            audioSource.connect(analyser);
            analyser.connect(audioCtx.destination);
            renderSpectrum();
        } catch (e) {
            console.log('Web Audio API initialized on user interaction');
        }
    }

    function playChimeSound() {
        if (!chimeToggle || !chimeToggle.checked) return Promise.resolve();
        return new Promise((resolve) => {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
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
        requestAnimationFrame(renderSpectrum);
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteFrequencyData(dataArray);

        const width = spectrumCanvas.width;
        const height = spectrumCanvas.height;
        canvasCtx.clearRect(0, 0, width, height);

        const barWidth = (width / bufferLength) * 1.5;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const barHeight = (dataArray[i] / 255) * height;
            const gradient = canvasCtx.createLinearGradient(0, height, 0, 0);
            gradient.addColorStop(0, '#9146ff');
            gradient.addColorStop(1, '#00f0ff');

            canvasCtx.fillStyle = gradient;
            canvasCtx.fillRect(x, height - barHeight, barWidth - 1, barHeight);
            x += barWidth + 1;
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
        updateQueueUI();
        updateNowPlayingUI(currentItem);

        if (currentItem.chunk_index === 1 && chimeToggle && chimeToggle.checked) {
            await playChimeSound();
        }

        audioPlayer.src = currentItem.url;
        audioPlayer.volume = volumeSlider.value / 100;
        
        audioPlayer.play().then(() => {
        }).catch(err => {
            console.error('Audio playback error:', err);
            isPlaying = false;
            checkAndPlayNext();
        });
    }

    // Global Hotkeys
    document.addEventListener('keydown', (e) => {
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
            return;
        }

        if (e.code === 'Space') {
            e.preventDefault();
            if (audioPlayer.paused && currentItem) {
                audioPlayer.play();
            } else {
                audioPlayer.pause();
            }
        } else if (e.code === 'KeyS') {
            skipBtn.click();
        } else if (e.code === 'KeyC') {
            clearBtn.click();
        } else if (e.code === 'KeyM') {
            muteBtn.click();
        }
    });

    audioPlayer.addEventListener('ended', () => {
        visualizer.classList.remove('playing');
        isPlaying = false;
        if (autoPlayToggle.checked) {
            checkAndPlayNext();
        }
    });

    audioPlayer.addEventListener('error', (e) => {
        console.error('Playback error on track:', e);
        visualizer.classList.remove('playing');
        isPlaying = false;
        checkAndPlayNext();
    });

    // Skip current audio track
    skipBtn.addEventListener('click', () => {
        if (isPlaying || audioPlayer.src) {
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
            visualizer.classList.remove('playing');
            isPlaying = false;
            checkAndPlayNext();
        }
    });

    // Clear entire queue
    clearBtn.addEventListener('click', () => {
        if (bufferTimer) {
            clearTimeout(bufferTimer);
            bufferTimer = null;
        }
        audioQueue = [];
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
        isPlaying = false;
        currentItem = null;
        visualizer.classList.remove('playing');
        updateNowPlayingUI(null);
        updateQueueUI();
    });

    // Volume & Mute Controls
    volumeSlider.addEventListener('input', () => {
        const val = volumeSlider.value;
        audioPlayer.volume = val / 100;
        volumeValue.textContent = `${val}%`;
        audioPlayer.muted = false;
        muteBtn.textContent = val == 0 ? '🔇' : '🔊';
    });

    muteBtn.addEventListener('click', () => {
        audioPlayer.muted = !audioPlayer.muted;
        muteBtn.textContent = audioPlayer.muted ? '🔇' : '🔊';
    });

    function updateQueueUI() {
        queueBadge.textContent = `${audioQueue.length} in queue`;
    }

    function updateNowPlayingUI(item) {
        if (!item) {
            speakerName.textContent = 'Idle / Ready';
            spokenText.textContent = 'Waiting for Twitch chat messages or manual test...';
            voiceTag.textContent = 'Voice: Default';
            chunkTag.textContent = 'Chunk: 0 / 0';
            return;
        }

        speakerName.textContent = item.user;
        spokenText.textContent = `"${item.text}"`;
        voiceTag.textContent = `Voice: ${item.voice || 'default'}`;
        chunkTag.textContent = `Chunk: ${item.chunk_index} / ${item.total_chunks}`;
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

        evtSource.addEventListener('error', (e) => {
            if (e.data) {
                try {
                    const errData = JSON.parse(e.data);
                    console.error('Server SSE error:', errData.message);
                } catch(err){}
            }
        });
    }

    // ----------------------------------------------------
    // API Actions & Forms
    // ----------------------------------------------------

    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                updateStatusUI(data);
            }
        } catch (e) {
            console.error('Failed to fetch status:', e);
        }
    }

    function updateStatusUI(data) {
        if (data.channel) {
            channelInput.value = data.channel;
        }
        if (data.connected && data.channel) {
            statusPill.classList.add('connected');
            statusText.textContent = `Connected: #${data.channel}`;
            connectBtn.textContent = 'Disconnect';
        } else {
            statusPill.classList.remove('connected');
            statusText.textContent = 'Disconnected';
            connectBtn.textContent = 'Connect';
        }

        if (data.config) {
            apiUrlInput.value = data.config.tts_api_url || '';
            defaultVoiceInput.value = data.config.tts_voice || '';
            formatSelect.value = data.config.tts_format || 'wav';
            maxChunkInput.value = data.config.max_chunk_chars || 100;
        }
    }

    // Connect / Disconnect Twitch Channel
    connectBtn.addEventListener('click', async () => {
        const targetChannel = channelInput.value.trim();
        if (!targetChannel) return;

        try {
            const res = await fetch('/api/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel: targetChannel })
            });
            if (res.ok) {
                fetchStatus();
            }
        } catch (e) {
            console.error('Failed to connect channel:', e);
        }
    });

    // Send Manual Test TTS
    sendTestBtn.addEventListener('click', async () => {
        const text = testTextInput.value.trim();
        if (!text) return;

        sendTestBtn.disabled = true;
        sendTestBtn.innerHTML = '<span>⏳</span> Synthesizing...';

        try {
            const res = await fetch('/api/tts/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    voice: testVoiceInput.value.trim() || null,
                    model: testModelInput.value.trim() || null,
                    user: 'TestUser'
                })
            });
            if (res.ok) {
                addChatMessage('TestUser', text);
            }
        } catch (e) {
            console.error('Failed to send test TTS:', e);
        } finally {
            sendTestBtn.disabled = false;
            sendTestBtn.innerHTML = '<span>🚀</span> Synthesize & Play';
        }
    });

    // Save Settings
    saveSettingsBtn.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tts_api_url: apiUrlInput.value.trim(),
                    tts_voice: defaultVoiceInput.value.trim(),
                    tts_format: formatSelect.value,
                    max_chunk_chars: parseInt(maxChunkInput.value, 10) || 100
                })
            });
            if (res.ok) {
                alert('Settings saved successfully!');
            }
        } catch (e) {
            console.error('Failed to save settings:', e);
        }
    });

    // Chat Feed
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
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
});
