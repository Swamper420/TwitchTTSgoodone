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
    const formatSelect = document.getElementById('formatSelect');
    const maxChunkInput = document.getElementById('maxChunkInput');
    const minChunkInput = document.getElementById('minChunkInput');
    const userTemplateInput = document.getElementById('userTemplateInput');
    const voicePresetsInput = document.getElementById('voicePresetsInput');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');

    const chatFeed = document.getElementById('chatFeed');
    const audioUnlockOverlay = document.getElementById('audioUnlockOverlay');
    const enableAudioBtn = document.getElementById('enableAudioBtn');
    const toastContainer = document.getElementById('toastContainer');
    const spectrumCanvas = document.getElementById('spectrumCanvas');
    const canvasCtx = spectrumCanvas ? spectrumCanvas.getContext('2d') : null;

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

        const barWidth = (width / bufferLength) * 1.5;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const barHeight = isPlaying ? (dataArray[i] / 255) * height : 2;
            const gradient = canvasCtx.createLinearGradient(0, height, 0, 0);
            gradient.addColorStop(0, '#9146ff');
            gradient.addColorStop(1, '#00f0ff');

            canvasCtx.fillStyle = gradient;
            canvasCtx.fillRect(x, height - barHeight, barWidth - 1, barHeight);
            x += barWidth + 1;
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

        // If this is chunk 1 of multi-chunk message, wait briefly for chunk 2 to buffer
        if (head.total_chunks > 1 && head.chunk_index === 1) {
            if (audioQueue.length < 2) {
                if (!bufferTimer) {
                    bufferTimer = setTimeout(() => {
                        bufferTimer = null;
                        if (!isPlaying && audioQueue.length > 0) {
                            playNextChunk();
                        }
                    }, 2500);
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

    async function playNextChunk() {
        if (bufferTimer) {
            clearTimeout(bufferTimer);
            bufferTimer = null;
        }

        if (audioQueue.length === 0) {
            isPlaying = false;
            currentItem = null;
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
    skipBtn.addEventListener('click', () => {
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
                    <span class="queue-item-user">#${idx + 1} - ${escapeHtml(item.user)} (${item.voice || 'default'})</span>
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
        voiceTag.textContent = `Voice: ${item.voice || 'default'}`;
        chunkTag.textContent = `Chunk: ${item.chunk_index} / ${item.total_chunks}`;
    }

    // ----------------------------------------------------
    // Voice Tag Chips Helper
    // ----------------------------------------------------

    if (voiceChips) {
        voiceChips.addEventListener('click', (e) => {
            if (e.target.classList.contains('chip')) {
                const voice = e.target.getAttribute('data-voice');
                if (voice) {
                    testTextInput.value = (testTextInput.value + ` [${voice}] `).trimStart();
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

        evtSource.addEventListener('error', (e) => {
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
            if (apiUrlInput) apiUrlInput.value = data.config.tts_api_url || '';
            if (defaultVoiceInput) defaultVoiceInput.value = data.config.tts_voice || '';
            if (defaultModelInput) defaultModelInput.value = data.config.tts_model || '';
            if (formatSelect) formatSelect.value = data.config.tts_format || 'wav';
            if (maxChunkInput) maxChunkInput.value = data.config.max_chunk_chars || 50;
            if (minChunkInput) minChunkInput.value = data.config.min_chunk_chars || 10;
            if (userTemplateInput) userTemplateInput.value = data.config.user_template || '';
            if (voicePresetsInput) voicePresetsInput.value = data.config.voice_presets || '';

            renderVoiceChips(data.config.voice_presets);
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
                showToast(`Connecting to Twitch channel #${targetChannel}...`, 'success');
                fetchStatus();
            }
        } catch (e) {
            console.error('Failed to connect channel:', e);
            showToast('Failed to connect to Twitch channel', 'error');
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
                showToast('TTS synthesis job queued!', 'success');
            } else {
                const errData = await res.json();
                showToast(`Synthesis failed: ${errData.error || 'Unknown error'}`, 'error');
            }
        } catch (e) {
            console.error('Failed to send test TTS:', e);
            showToast('Failed to connect to backend server', 'error');
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
                    tts_api_url: apiUrlInput ? apiUrlInput.value.trim() : '',
                    tts_voice: defaultVoiceInput ? defaultVoiceInput.value.trim() : '',
                    tts_model: defaultModelInput ? defaultModelInput.value.trim() : '',
                    tts_format: formatSelect ? formatSelect.value : 'wav',
                    max_chunk_chars: maxChunkInput ? (parseInt(maxChunkInput.value, 10) || 50) : 50,
                    min_chunk_chars: minChunkInput ? (parseInt(minChunkInput.value, 10) || 10) : 10,
                    user_template: userTemplateInput ? userTemplateInput.value.trim() : '',
                    voice_presets: voicePresetsInput ? voicePresetsInput.value.trim() : ''
                })
            });
            if (res.ok) {
                showToast('Settings saved persistently!', 'success');
                fetchStatus();
            } else {
                showToast('Failed to save settings', 'error');
            }
        } catch (e) {
            console.error('Failed to save settings:', e);
            showToast('Failed to save settings', 'error');
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
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Toast Notification Helper
    function showToast(message, type = 'info') {
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icon = type === 'error' ? '❌' : type === 'success' ? '✅' : 'ℹ️';
        toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
});
