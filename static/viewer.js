// Twitch TTS Viewer Hub - Interactive Application Logic

document.addEventListener('DOMContentLoaded', () => {
    // State Stores
    let commandsData = [];
    let voicesData = [];
    let userVoicesData = {};
    let soundboardList = [];
    let activeChannel = '';
    let selectedFileBytes = null;
    let selectedFileName = '';

    // DOM Elements
    const statusPill = document.getElementById('statusPill');
    const statusText = document.getElementById('statusText');
    const activeChannelDisplay = document.getElementById('activeChannelDisplay');
    const toastContainer = document.getElementById('toastContainer');

    // Tabs
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    // Generator DOM
    const messageInput = document.getElementById('messageInput');
    const parseChunksContainer = document.getElementById('parseChunksContainer');
    const voiceTagChips = document.getElementById('voiceTagChips');
    const soundTagChips = document.getElementById('soundTagChips');
    const addPierutaBtn = document.getElementById('addPierutaBtn');
    const copyMessageBtn = document.getElementById('copyMessageBtn');
    const previewTTSBtn = document.getElementById('previewTTSBtn');
    const auditionAudioPlayer = document.getElementById('auditionAudioPlayer');
    const auditionStatus = document.getElementById('auditionStatus');

    // Search DOMs
    const commandSearch = document.getElementById('commandSearch');
    const commandsGrid = document.getElementById('commandsGrid');
    const voiceSearch = document.getElementById('voiceSearch');
    const voicesGrid = document.getElementById('voicesGrid');
    const soundSearch = document.getElementById('soundSearch');
    const soundsCatalogGrid = document.getElementById('soundsCatalogGrid');

    // Upload DOMs
    const uploadSoundForm = document.getElementById('uploadSoundForm');
    const streamerPasswordInput = document.getElementById('streamerPasswordInput');
    const soundNameInput = document.getElementById('soundNameInput');
    const dragDropZone = document.getElementById('dragDropZone');
    const audioFileInput = document.getElementById('audioFileInput');
    const selectedFileInfo = document.getElementById('selectedFileInfo');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const fileSizeDisplay = document.getElementById('fileSizeDisplay');
    const uploadSubmitBtn = document.getElementById('uploadSubmitBtn');

    // Initialize Application
    initApp();

    async function initApp() {
        setupTabs();
        setupDragAndDrop();
        setupGeneratorEvents();
        setupSearchFilters();

        await fetchStatus();
        await fetchCommands();
        await fetchVoices();
        await fetchSoundboard();
        connectSSE();
    }

    // Toast Notification System
    function showToast(msg, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icon = type === 'success' ? 'check_circle' : 'error';
        toast.innerHTML = `<span class="material-symbols-outlined">${icon}</span><span>${escapeHtml(msg)}</span>`;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Tabs Switcher
    function setupTabs() {
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTab = btn.getAttribute('data-tab');
                tabBtns.forEach(b => b.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));

                btn.classList.add('active');
                const targetEl = document.getElementById(targetTab);
                if (targetEl) targetEl.classList.add('active');
            });
        });
    }

    // Fetch Status & Channels
    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                activeChannel = data.channel || (data.channels && data.channels[0]) || '';

                if (data.connected && activeChannel) {
                    statusPill.classList.add('connected');
                    statusText.textContent = 'Live Monitored';
                    activeChannelDisplay.textContent = `@${activeChannel}`;
                } else {
                    statusPill.classList.remove('connected');
                    statusText.textContent = 'Standby';
                    activeChannelDisplay.textContent = activeChannel ? `@${activeChannel} (Offline)` : 'No Channel Active';
                }
            }
        } catch (e) {
            console.warn('Status check failed:', e);
        }
    }

    // SSE Connection for Live Updates
    function connectSSE() {
        try {
            const evtSource = new EventSource('/api/events');
            evtSource.onmessage = (e) => {
                try {
                    const eventData = JSON.parse(e.data);
                    if (eventData.event === 'soundboard_updated') {
                        fetchSoundboard();
                    }
                } catch (err) {}
            };
        } catch (err) {
            console.log('SSE notification connect omitted or auth required.');
        }
    }

    // Fetch Commands Catalog
    async function fetchCommands() {
        try {
            const res = await fetch('/api/commands');
            if (res.ok) {
                const data = await res.json();
                commandsData = data.commands || [];
                renderCommands(commandsData);
            }
        } catch (e) {
            commandsGrid.innerHTML = '<div class="loading-spinner">Failed to load chat commands.</div>';
        }
    }

    function renderCommands(list) {
        if (!list || list.length === 0) {
            commandsGrid.innerHTML = '<div class="loading-spinner">No matching commands found.</div>';
            return;
        }

        commandsGrid.innerHTML = list.map(cmd => `
            <div class="cmd-card">
                <div class="cmd-header">
                    <span class="cmd-name">${escapeHtml(cmd.name)}</span>
                    <span class="badge badge-purple">${escapeHtml(cmd.category)}</span>
                </div>
                <div class="cmd-syntax">${escapeHtml(cmd.syntax)}</div>
                <p class="cmd-desc">${escapeHtml(cmd.description)}</p>
                <div class="cmd-aliases">
                    ${(cmd.aliases || []).map(a => `<span class="alias-chip">${escapeHtml(a)}</span>`).join('')}
                </div>
            </div>
        `).join('');
    }

    // Fetch Voices List
    async function fetchVoices() {
        try {
            const [vRes, uvRes] = await Promise.all([
                fetch('/api/voices').catch(() => null),
                fetch('/api/user_voices').catch(() => null)
            ]);

            if (vRes && vRes.ok) {
                const data = await vRes.json();
                voicesData = data.voices || data.presets || [];
            }
            if (uvRes && uvRes.ok) {
                const data = await uvRes.json();
                userVoicesData = data.user_voices || {};
            }

            renderVoices();
            populateVoiceChips();
        } catch (e) {
            voicesGrid.innerHTML = '<div class="loading-spinner">Failed to load voice presets.</div>';
        }
    }

    function renderVoices() {
        let combined = [];
        if (Array.isArray(voicesData)) {
            combined = voicesData.map(v => typeof v === 'string' ? { name: v } : v);
        }

        const filterText = (voiceSearch.value || '').toLowerCase().trim();
        const filtered = combined.filter(v => (v.name || '').toLowerCase().includes(filterText));

        if (filtered.length === 0) {
            voicesGrid.innerHTML = '<div class="loading-spinner">No voice presets match your query.</div>';
            return;
        }

        voicesGrid.innerHTML = filtered.map(v => {
            const name = v.name || 'Voice';
            return `
                <div class="voice-card">
                    <div class="voice-header">
                        <span class="sound-title" style="color: var(--accent-purple); font-weight:700;">${escapeHtml(name)}</span>
                        <button class="icon-btn audition-voice-btn" data-voice="${escapeHtml(name)}" title="Sample Voice">
                            <span class="material-symbols-outlined" style="font-size:18px;">play_arrow</span>
                        </button>
                    </div>
                    <p class="cmd-desc">Preset TTS voice. Click play to audition or use command <code>!myvoice ${escapeHtml(name)}</code> in chat.</p>
                </div>
            `;
        }).join('');

        // Attach audition button listeners
        document.querySelectorAll('.audition-voice-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const vName = btn.getAttribute('data-voice');
                auditionVoiceSample(vName);
            });
        });
    }

    function populateVoiceChips() {
        let chipsHtml = `
            <button type="button" class="chip-btn" data-insert="!myvoice mieto ">!myvoice mieto</button>
            <button type="button" class="chip-btn" data-insert="!myvoice random ">!myvoice random</button>
            <button type="button" class="chip-btn" data-insert="!myvoice reset ">!myvoice reset</button>
        `;

        if (Array.isArray(voicesData)) {
            const presets = voicesData.slice(0, 5);
            presets.forEach(p => {
                const pname = typeof p === 'string' ? p : p.name;
                if (pname && pname !== 'mieto') {
                    chipsHtml += `<button type="button" class="chip-btn" data-insert="!myvoice ${escapeHtml(pname)} ">!myvoice ${escapeHtml(pname)}</button>`;
                }
            });
        }
        voiceTagChips.innerHTML = chipsHtml;
        bindChipInsertButtons();
    }

    // Fetch Soundboard Catalog
    async function fetchSoundboard() {
        try {
            const res = await fetch('/api/soundboard');
            if (res.ok) {
                const data = await res.json();
                soundboardList = data.sounds || [];
                renderSoundboard();
                populateSoundChips();
            }
        } catch (e) {
            soundsCatalogGrid.innerHTML = '<div class="loading-spinner">Failed to load soundboard list.</div>';
        }
    }

    function renderSoundboard() {
        const filterText = (soundSearch.value || '').toLowerCase().trim();
        const filtered = soundboardList.filter(s => s.toLowerCase().includes(filterText));

        if (filtered.length === 0) {
            soundsCatalogGrid.innerHTML = '<div class="loading-spinner">No sound effects available. Upload one on the left!</div>';
            return;
        }

        soundsCatalogGrid.innerHTML = filtered.map(sound => `
            <div class="sound-card">
                <span class="sound-title">(${escapeHtml(sound)})</span>
                <div class="sound-card-actions">
                    <button class="icon-btn play-sound-btn" data-sound="${escapeHtml(sound)}" title="Play Audio Preview">
                        <span class="material-symbols-outlined" style="font-size:18px;">volume_up</span>
                    </button>
                    <button class="icon-btn insert-sound-btn" data-sound="${escapeHtml(sound)}" title="Insert trigger into Message Generator">
                        <span class="material-symbols-outlined" style="font-size:18px;">add</span>
                    </button>
                </div>
            </div>
        `).join('');

        // Attach listeners
        document.querySelectorAll('.play-sound-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const sound = btn.getAttribute('data-sound');
                playAudioPreview(`/api/soundboard/${encodeURIComponent(sound)}`, `Sound effect: (${sound})`);
            });
        });

        document.querySelectorAll('.insert-sound-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const sound = btn.getAttribute('data-sound');
                insertIntoMessage(`(${sound}) `);
                showToast(`Inserted trigger (${sound}) into message builder`);
            });
        });
    }

    function populateSoundChips() {
        if (!soundboardList || soundboardList.length === 0) {
            soundTagChips.innerHTML = '<span class="placeholder-text">No sounds uploaded yet.</span>';
            return;
        }
        soundTagChips.innerHTML = soundboardList.slice(0, 12).map(s => `
            <button type="button" class="chip-btn chip-btn-sound" data-insert="(${escapeHtml(s)}) ">(${escapeHtml(s)})</button>
        `).join('');
        bindChipInsertButtons();
    }

    function bindChipInsertButtons() {
        document.querySelectorAll('.chip-btn[data-insert]').forEach(btn => {
            btn.replaceWith(btn.cloneNode(true));
        });
        document.querySelectorAll('.chip-btn[data-insert]').forEach(btn => {
            btn.addEventListener('click', () => {
                const textToInsert = btn.getAttribute('data-insert');
                insertIntoMessage(textToInsert);
            });
        });
    }

    function insertIntoMessage(text) {
        const start = messageInput.selectionStart || messageInput.value.length;
        const end = messageInput.selectionEnd || messageInput.value.length;
        const val = messageInput.value;
        messageInput.value = val.substring(0, start) + text + val.substring(end);
        messageInput.focus();
        messageInput.setSelectionRange(start + text.length, start + text.length);
        updateLiveParseBreakdown();
    }

    // Message Generator Logic & Live Parser
    function setupGeneratorEvents() {
        messageInput.addEventListener('input', updateLiveParseBreakdown);

        addPierutaBtn.addEventListener('click', () => {
            insertIntoMessage('!pieruta ');
        });

        copyMessageBtn.addEventListener('click', () => {
            const val = messageInput.value.trim();
            if (!val) {
                showToast('Please type a message first', 'error');
                return;
            }
            navigator.clipboard.writeText(val).then(() => {
                showToast('Copied message to clipboard for Twitch Chat!');
            }).catch(() => {
                showToast('Failed to copy. Please copy manually.', 'error');
            });
        });

        previewTTSBtn.addEventListener('click', async () => {
            const val = messageInput.value.trim();
            if (!val) {
                showToast('Please enter a message to audition', 'error');
                return;
            }

            auditionStatus.textContent = 'Synthesizing TTS Audio Preview...';
            previewTTSBtn.disabled = true;

            try {
                const ttsUrl = `/api/tts?text=${encodeURIComponent(val)}`;
                playAudioPreview(ttsUrl, `Auditioning: "${val.slice(0, 30)}..."`);
            } catch (err) {
                showToast('TTS Audition failed', 'error');
            } finally {
                previewTTSBtn.disabled = false;
            }
        });
    }

    function updateLiveParseBreakdown() {
        const text = messageInput.value;
        if (!text.trim()) {
            parseChunksContainer.innerHTML = `
                <div class="empty-parse-state">
                    <span class="material-symbols-outlined">find_in_page</span>
                    <p>Start typing above to see how Twitch TTS splits text into voice segments and sound triggers.</p>
                </div>
            `;
            return;
        }

        // Split text by sound triggers (sound_name)
        const pattern = /\(([^()\n]+)\)/g;
        let segments = [];
        let lastIdx = 0;
        let match;

        while ((match = pattern.exec(text)) !== null) {
            if (match.index > lastIdx) {
                segments.push({ type: 'text', content: text.substring(lastIdx, match.index) });
            }
            segments.push({ type: 'sound', content: match[1], raw: match[0] });
            lastIdx = pattern.lastIndex;
        }
        if (lastIdx < text.length) {
            segments.push({ type: 'text', content: text.substring(lastIdx) });
        }

        parseChunksContainer.innerHTML = segments.map((seg, idx) => {
            if (seg.type === 'sound') {
                return `
                    <div class="chunk-card chunk-card-sound">
                        <span>🔊 Sound Effect: <strong>(${escapeHtml(seg.content)})</strong></span>
                        <span class="badge badge-cyan">Trigger</span>
                    </div>
                `;
            } else {
                return `
                    <div class="chunk-card chunk-card-text">
                        <span>💬 TTS Text: "${escapeHtml(seg.content)}"</span>
                        <span class="chunk-voice-tag">Voice Segment</span>
                    </div>
                `;
            }
        }).join('');
    }

    // Audio Playback Helper
    function playAudioPreview(url, title) {
        auditionStatus.textContent = title || 'Playing preview...';
        auditionAudioPlayer.src = url;
        auditionAudioPlayer.play().catch(e => {
            console.warn('Audio playback error:', e);
            showToast('Click play on the audition player below to listen.', 'error');
        });
    }

    function auditionVoiceSample(vName) {
        const sampleText = `Hello! This is a voice sample for ${vName}.`;
        const url = `/api/tts?text=${encodeURIComponent(sampleText)}&voice=${encodeURIComponent(vName)}`;
        playAudioPreview(url, `Auditioning Voice: ${vName}`);
    }

    // Search Filters
    function setupSearchFilters() {
        if (commandSearch) commandSearch.addEventListener('input', () => {
            const query = commandSearch.value.toLowerCase().trim();
            const filtered = commandsData.filter(c => 
                c.name.toLowerCase().includes(query) || 
                c.syntax.toLowerCase().includes(query) ||
                (c.aliases || []).some(a => a.toLowerCase().includes(query))
            );
            renderCommands(filtered);
        });

        if (voiceSearch) voiceSearch.addEventListener('input', renderVoices);
        if (soundSearch) soundSearch.addEventListener('input', renderSoundboard);
    }

    // File Upload with Drag & Drop and Pre-Validation
    function setupDragAndDrop() {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dragDropZone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            dragDropZone.addEventListener(eventName, () => dragDropZone.classList.add('dragover'), false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dragDropZone.addEventListener(eventName, () => dragDropZone.classList.remove('dragover'), false);
        });

        dragDropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                handleSelectedFile(files[0]);
            }
        });

        audioFileInput.addEventListener('change', () => {
            if (audioFileInput.files && audioFileInput.files.length > 0) {
                handleSelectedFile(audioFileInput.files[0]);
            }
        });

        uploadSoundForm.addEventListener('submit', handleFormSubmit);
    }

    function handleSelectedFile(file) {
        const allowedExts = ['.mp3', '.wav', '.ogg', '.flac', '.m4a'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        if (!allowedExts.includes(ext)) {
            showToast(`Unsupported extension "${ext}". Allowed: ${allowedExts.join(', ')}`, 'error');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showToast(`File size (${(file.size / 1048576).toFixed(1)} MB) exceeds 5MB limit.`, 'error');
            return;
        }

        // Auto populate sound name if empty
        if (!soundNameInput.value.trim()) {
            const rawBase = file.name.substring(0, file.name.lastIndexOf('.'));
            const cleanBase = rawBase.toLowerCase().replace(/[^a-z0-9_\-]/g, '');
            soundNameInput.value = cleanBase;
        }

        selectedFileName = file.name;
        fileNameDisplay.textContent = file.name;
        fileSizeDisplay.textContent = `${(file.size / 1048576).toFixed(2)} MB`;
        selectedFileInfo.classList.remove('hidden');

        // Read file bytes as Base64
        const reader = new FileReader();
        reader.onload = function(e) {
            selectedFileBytes = e.target.result;
            uploadSubmitBtn.disabled = false;
        };
        reader.readAsDataURL(file);
    }

    async function handleFormSubmit(e) {
        e.preventDefault();

        const password = streamerPasswordInput.value.trim();
        const soundName = soundNameInput.value.trim();

        if (!password) {
            showToast('Streamer Password (Active Channel Name) is required.', 'error');
            return;
        }

        if (!soundName || soundName.length < 2) {
            showToast('Sound name must be at least 2 characters (alphanumeric, -, _).', 'error');
            return;
        }

        if (!selectedFileBytes) {
            showToast('Please select or drop an audio file first.', 'error');
            return;
        }

        uploadSubmitBtn.disabled = true;
        uploadSubmitBtn.innerHTML = '<span class="material-symbols-outlined spinning">sync</span> Validating & Uploading...';

        try {
            const payload = {
                filename: selectedFileName,
                sound_name: soundName,
                streamer_password: password,
                file_b64: selectedFileBytes
            };

            const res = await fetch('/api/soundboard/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json();

            if (res.ok && data.success) {
                showToast(data.message || `Sound (${data.sound_name}) uploaded successfully!`);
                uploadSoundForm.reset();
                selectedFileBytes = null;
                selectedFileInfo.classList.add('hidden');
                await fetchSoundboard();
            } else {
                showToast(data.error || 'Upload failed validation.', 'error');
            }
        } catch (err) {
            showToast('Network error during upload request.', 'error');
        } finally {
            uploadSubmitBtn.disabled = false;
            uploadSubmitBtn.innerHTML = '<span class="material-symbols-outlined">upload</span> Upload & Register Sound';
        }
    }
});
