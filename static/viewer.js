// Twitch TTS Viewer Hub - Windows 95 Soundboard Main Edition Logic

document.addEventListener('DOMContentLoaded', () => {
    // State Stores
    let commandsData = [];
    let soundboardList = [];
    let activeChannel = '';
    let selectedFileBytes = null;
    let selectedFileName = '';
    // Black Mesa security checkpoint state (one pass per file, server-verified)
    let hl2Challenge = null;
    let hl2UploadToken = null;
    let hl2ClearedFileKey = null;

    // DOM Elements
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const activeChannelDisplay = document.getElementById('activeChannelDisplay');
    const toastContainer = document.getElementById('toastContainer');

    // Tabs
    const tabBtns = document.querySelectorAll('.win95-tab');
    const tabContents = document.querySelectorAll('.tab-content');

    // Player DOM
    const auditionAudioPlayer = document.getElementById('auditionAudioPlayer');
    const auditionStatus = document.getElementById('auditionStatus');

    // Search DOMs
    const commandSearch = document.getElementById('commandSearch');
    const commandsTableBody = document.getElementById('commandsTableBody');
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
    const localFilePreviewPlayer = document.getElementById('localFilePreviewPlayer');
    const uploadSubmitBtn = document.getElementById('uploadSubmitBtn');

    // Black Mesa Checkpoint DOMs
    const hl2StatusLight = document.getElementById('hl2StatusLight');
    const hl2StatusText = document.getElementById('hl2StatusText');
    const hl2Prompt = document.getElementById('hl2Prompt');
    const hl2GameArea = document.getElementById('hl2GameArea');
    const hl2NewChallengeBtn = document.getElementById('hl2NewChallengeBtn');
    const hl2VerifyBtn = document.getElementById('hl2VerifyBtn');

    // Password Modal DOMs
    const passwordModal = document.getElementById('passwordModal');
    const modalPasswordInput = document.getElementById('modalPasswordInput');
    const rememberPasswordCheck = document.getElementById('rememberPasswordCheck');
    const modalOkBtn = document.getElementById('modalOkBtn');
    const modalCancelBtn = document.getElementById('modalCancelBtn');
    const modalCloseBtn = document.getElementById('modalCloseBtn');
    const menuLogonBtn = document.getElementById('menuLogonBtn');

    // Initialize Application
    initApp();

    async function initApp() {
        setupPasswordModal();
        setupTabs();
        setupDragAndDrop();
        setupSearchFilters();
        setupHl2Checkpoint();

        await fetchStatus();
        await fetchSoundboard();
        await fetchCommands();
        connectSSE();
    }

    // Password Logon Modal Handler
    function setupPasswordModal() {
        const savedPass = localStorage.getItem('twitch_tts_streamer_password') || sessionStorage.getItem('twitch_tts_streamer_password');
        
        if (savedPass) {
            if (streamerPasswordInput) streamerPasswordInput.value = savedPass;
            if (passwordModal) passwordModal.classList.add('hidden');
        } else {
            if (passwordModal) {
                passwordModal.classList.remove('hidden');
                setTimeout(() => modalPasswordInput && modalPasswordInput.focus(), 100);
            }
        }

        function submitPassword() {
            const pass = modalPasswordInput ? modalPasswordInput.value.trim() : '';
            if (!pass) {
                showToast('Please enter a password', 'error');
                return;
            }
            if (rememberPasswordCheck && rememberPasswordCheck.checked) {
                localStorage.setItem('twitch_tts_streamer_password', pass);
            } else {
                sessionStorage.setItem('twitch_tts_streamer_password', pass);
            }
            if (streamerPasswordInput) streamerPasswordInput.value = pass;
            if (passwordModal) passwordModal.classList.add('hidden');
            showToast(`Password set: @${pass}`);
        }

        if (modalOkBtn) modalOkBtn.addEventListener('click', submitPassword);
        if (modalPasswordInput) {
            modalPasswordInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') submitPassword();
            });
        }

        if (modalCancelBtn) modalCancelBtn.addEventListener('click', () => {
            if (passwordModal) passwordModal.classList.add('hidden');
        });

        if (modalCloseBtn) modalCloseBtn.addEventListener('click', () => {
            if (passwordModal) passwordModal.classList.add('hidden');
        });

        if (menuLogonBtn) menuLogonBtn.addEventListener('click', () => {
            if (modalPasswordInput) modalPasswordInput.value = streamerPasswordInput.value || '';
            if (passwordModal) {
                passwordModal.classList.remove('hidden');
                setTimeout(() => modalPasswordInput && modalPasswordInput.focus(), 100);
            }
        });
    }

    // Win95 Toast Notification System
    function showToast(msg, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const icon = type === 'success' ? '✅' : '⚠️';
        toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(msg)}</span>`;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Win95 Tab Switcher
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

    // Fetch Status & Active Channel
    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                activeChannel = data.channel || (data.channels && data.channels[0]) || '';

                if (data.connected && activeChannel) {
                    statusDot.classList.add('online');
                    statusText.textContent = 'ONLINE (LIVE MONITORED)';
                    activeChannelDisplay.textContent = `@${activeChannel.toUpperCase()}`;
                } else {
                    statusDot.classList.remove('online');
                    statusText.textContent = 'STANDBY';
                    activeChannelDisplay.textContent = activeChannel ? `@${activeChannel.toUpperCase()} (OFFLINE)` : 'NO CHANNEL';
                }
            }
        } catch (e) {
            console.warn('Status check failed:', e);
            statusText.textContent = 'STATUS CHECK FAILED';
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
        } catch (err) {}
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
            if (commandsTableBody) {
                commandsTableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Failed to load chat commands.</td></tr>';
            }
        }
    }

    function renderCommands(list) {
        if (!commandsTableBody) return;

        if (!list || list.length === 0) {
            commandsTableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No matching chat commands found.</td></tr>';
            return;
        }

        commandsTableBody.innerHTML = list.map(cmd => `
            <tr>
                <td><strong>${escapeHtml(cmd.name)}</strong></td>
                <td><span class="win95-chip">${escapeHtml(cmd.category)}</span></td>
                <td><code>${escapeHtml(cmd.syntax)}</code></td>
                <td>${escapeHtml(cmd.description)}</td>
                <td>
                    ${(cmd.aliases || []).map(a => `<span class="win95-chip">${escapeHtml(a)}</span>`).join(' ')}
                </td>
            </tr>
        `).join('');
    }

    // Fetch Soundboard Catalog
    async function fetchSoundboard() {
        try {
            const res = await fetch('/api/soundboard');
            if (res.ok) {
                const data = await res.json();
                soundboardList = data.sounds || [];
                renderSoundboard();
            }
        } catch (e) {
            if (soundsCatalogGrid) {
                soundsCatalogGrid.innerHTML = '<div style="color: #666; text-align: center; grid-column: 1/-1;">Failed to load soundboard list.</div>';
            }
        }
    }

    function renderSoundboard() {
        if (!soundsCatalogGrid) return;
        const filterText = (soundSearch && soundSearch.value || '').toLowerCase().trim();
        const filtered = soundboardList.filter(s => s.toLowerCase().includes(filterText));

        if (filtered.length === 0) {
            soundsCatalogGrid.innerHTML = '<div style="color: #666; text-align: center; grid-column: 1/-1;">No sound effects available.</div>';
            return;
        }

        soundsCatalogGrid.innerHTML = filtered.map(sound => `
            <div class="win95-card">
                <div>
                    <div class="win95-card-title">🔊 (${escapeHtml(sound)})</div>
                    <div class="win95-card-desc">Type <code>(${escapeHtml(sound)})</code> in Twitch Chat</div>
                </div>
                <div class="win95-card-actions">
                    <button type="button" class="win95-btn play-sound-btn" data-sound="${escapeHtml(sound)}">▶️ Play</button>
                    <button type="button" class="win95-btn copy-sound-btn" data-sound="${escapeHtml(sound)}">📋 Copy Tag</button>
                </div>
            </div>
        `).join('');

        // Attach listeners
        document.querySelectorAll('.play-sound-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const sound = btn.getAttribute('data-sound');
                playAudioPreview(`/api/soundboard/${encodeURIComponent(sound)}`, `Playing: (${sound})`);
            });
        });

        document.querySelectorAll('.copy-sound-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const sound = btn.getAttribute('data-sound');
                const tag = `(${sound})`;
                navigator.clipboard.writeText(tag).then(() => {
                    showToast(`Copied ${tag} tag to clipboard!`);
                }).catch(() => {
                    showToast(`Copied ${tag}`);
                });
            });
        });
    }

    // Audio Playback Helper
    function playAudioPreview(url, title) {
        if (auditionStatus) auditionStatus.textContent = title.toUpperCase() || 'PLAYING AUDIO...';
        if (auditionAudioPlayer) {
            auditionAudioPlayer.src = url;
            auditionAudioPlayer.play().catch(e => {
                console.warn('Audio playback error:', e);
                showToast('Click play on media player below to listen.', 'error');
            });
        }
    }

    // Search Filters
    function setupSearchFilters() {
        if (commandSearch) {
            commandSearch.addEventListener('input', () => {
                const query = commandSearch.value.toLowerCase().trim();
                const filtered = commandsData.filter(c => 
                    c.name.toLowerCase().includes(query) || 
                    c.syntax.toLowerCase().includes(query) ||
                    (c.aliases || []).some(a => a.toLowerCase().includes(query))
                );
                renderCommands(filtered);
            });
        }

        if (soundSearch) soundSearch.addEventListener('input', renderSoundboard);
    }

    // File Upload & Local Audio Pre-playback
    function setupDragAndDrop() {
        if (!dragDropZone) return;

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

        if (audioFileInput) {
            audioFileInput.addEventListener('change', () => {
                if (audioFileInput.files && audioFileInput.files.length > 0) {
                    handleSelectedFile(audioFileInput.files[0]);
                }
            });
        }

        if (uploadSoundForm) uploadSoundForm.addEventListener('submit', handleFormSubmit);
    }

    function currentFileKey() {
        if (!selectedFileName || !selectedFileBytes) return '';
        return selectedFileName + '::' + String(selectedFileBytes.length) + '::' + String(selectedFileBytes.slice(0, 64));
    }

    function refreshUploadButton() {
        if (!uploadSubmitBtn) return;
        const hasFile = !!selectedFileBytes;
        const cleared = hl2UploadToken && hl2ClearedFileKey && hl2ClearedFileKey === currentFileKey();
        if (!hasFile) {
            uploadSubmitBtn.disabled = true;
            uploadSubmitBtn.textContent = '💾 Upload & Register Sound';
        } else if (!cleared) {
            uploadSubmitBtn.disabled = true;
            uploadSubmitBtn.textContent = '🔒 Upload Locked — Pass Security Check';
        } else {
            uploadSubmitBtn.disabled = false;
            uploadSubmitBtn.textContent = '💾 Upload & Register Sound';
        }
    }

    function resetHl2Clearance(reason) {
        hl2UploadToken = null;
        hl2ClearedFileKey = null;
        refreshUploadButton();
        if (reason) setHl2Status('lock', reason);
    }

    function handleSelectedFile(file) {
        const allowedExts = ['.mp3', '.wav', '.ogg', '.flac', '.m4a'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        if (!allowedExts.includes(ext)) {
            showToast(`Unsupported extension "${ext}".`, 'error');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showToast(`File size (${(file.size / 1048576).toFixed(1)} MB) exceeds 5MB limit.`, 'error');
            return;
        }

        if (!soundNameInput.value.trim()) {
            const rawBase = file.name.substring(0, file.name.lastIndexOf('.'));
            const cleanBase = rawBase.toLowerCase().replace(/[^a-z0-9_\-]/g, '');
            soundNameInput.value = cleanBase;
        }

        selectedFileName = file.name;
        fileNameDisplay.textContent = file.name;
        fileSizeDisplay.textContent = `${(file.size / 1048576).toFixed(2)} MB`;

        // A new file always voids prior clearance: one minigame pass == one file.
        resetHl2Clearance('');

        // Setup local audio preview player
        const objectUrl = URL.createObjectURL(file);
        if (localFilePreviewPlayer) localFilePreviewPlayer.src = objectUrl;

        if (selectedFileInfo) selectedFileInfo.classList.remove('hidden');

        // Read bytes as Base64 for submission
        const reader = new FileReader();
        reader.onload = function(e) {
            selectedFileBytes = e.target.result;
            // Selecting a new file invalidates any earlier clearance.
            hl2UploadToken = null;
            hl2ClearedFileKey = null;
            refreshUploadButton();
            setHl2Status('lock', 'New file detected — pass a fresh security check to unlock upload.');
            // Convenience: auto-summon a new challenge for the new file.
            requestHl2Challenge(true);
        };
        reader.readAsDataURL(file);
    }

    async function handleFormSubmit(e) {
        e.preventDefault();

        const password = streamerPasswordInput.value.trim();
        const soundName = soundNameInput.value.trim();

        if (!password) {
            showToast('Streamer Password is required.', 'error');
            return;
        }

        if (!soundName || soundName.length < 2) {
            showToast('Sound name must be at least 2 chars.', 'error');
            return;
        }

        if (!selectedFileBytes) {
            showToast('Please select or drop an audio file.', 'error');
            return;
        }

        // Client-side gate (UX only — the server re-verifies the token and
        // rejects the upload with 403 if it is missing, reused, or expired).
        if (!hl2UploadToken || hl2ClearedFileKey !== currentFileKey()) {
            showToast('Complete the Black Mesa security check first — one pass per file.', 'error');
            requestHl2Challenge(true);
            return;
        }

        if (uploadSubmitBtn) {
            uploadSubmitBtn.disabled = true;
            uploadSubmitBtn.textContent = '⏳ VALIDATING & UPLOADING...';
        }

        try {
            const payload = {
                filename: selectedFileName,
                sound_name: soundName,
                streamer_password: password,
                file_b64: selectedFileBytes,
                upload_token: hl2UploadToken
            };

            const res = await fetch('/api/soundboard/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await res.json().catch(() => ({}));

            if (res.ok && data.success) {
                showToast(data.message || `Sound (${data.sound_name}) uploaded successfully!`);
                uploadSoundForm.reset();
                selectedFileBytes = null;
                if (selectedFileInfo) selectedFileInfo.classList.add('hidden');
                // Burn client copy too: each file needs a fresh pass.
                hl2UploadToken = null;
                hl2ClearedFileKey = null;
                hl2Challenge = null;
                if (hl2GameArea) hl2GameArea.innerHTML = '';
                if (hl2Prompt) hl2Prompt.textContent = 'Clearance spent. Summon a new check for your next file, citizen.';
                setHl2Status('lock', 'CLEARANCE SPENT — one pass per file. New upload needs a new check.');
                refreshUploadButton();
                await fetchSoundboard();
            } else {
                if (res.status === 403 && data.minigame_required) {
                    showToast(data.error || 'Security check required.', 'error');
                    resetHl2Clearance('LOCKDOWN: clearance rejected — pass the check again.');
                    requestHl2Challenge(true);
                } else {
                    showToast(data.error || 'Upload failed validation.', 'error');
                }
            }
        } catch (err) {
            showToast('Network error during upload request.', 'error');
        } finally {
            refreshUploadButton();
        }
    }

    // ── Black Mesa Security Checkpoint (HL2 minigame, server-verified) ──
    function setHl2Status(mode, text) {
        if (hl2StatusText) {
            hl2StatusText.textContent = text;
            hl2StatusText.classList.toggle('granted', mode === 'granted');
        }
        if (hl2StatusLight) {
            hl2StatusLight.className = 'hl2-light ' + (
                mode === 'granted' ? 'hl2-light-green' : mode === 'working' ? 'hl2-light-amber' : 'hl2-light-red'
            );
        }
    }

    function symbolMeta(id) {
        const found = (hl2Challenge && hl2Challenge.payload && hl2Challenge.payload.symbols || [])
            .find(s => s.id === id);
        if (found) return found;
        return { id, icon: '❔', label: id };
    }

    function setupHl2Checkpoint() {
        if (hl2NewChallengeBtn) hl2NewChallengeBtn.addEventListener('click', () => requestHl2Challenge(false));
        if (hl2VerifyBtn) hl2VerifyBtn.addEventListener('click', verifyHl2Solution);
        refreshUploadButton();
    }

    async function requestHl2Challenge(silent) {
        if (!hl2GameArea) return;
        setHl2Status('working', 'CONTACTING BLACK MESA… summoning randomized challenge.');
        if (hl2VerifyBtn) hl2VerifyBtn.disabled = true;
        hl2GameArea.innerHTML = '<p class="hl2-prompt">📡 Uplink… the Administrator is choosing your trial.</p>';
        try {
            const res = await fetch('/api/upload-challenge/request', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                setHl2Status('lock', 'UPLINK FAILED: ' + (data.error || 'could not summon challenge.'));
                hl2GameArea.innerHTML = '';
                return;
            }
            hl2Challenge = data;
            // New challenge voids any previous clearance.
            hl2UploadToken = null;
            hl2ClearedFileKey = null;
            refreshUploadButton();
            renderHl2Challenge();
        } catch (err) {
            setHl2Status('lock', 'UPLINK FAILED: network error contacting Black Mesa.');
            hl2GameArea.innerHTML = '';
            if (!silent) showToast('Could not reach security checkpoint.', 'error');
        }
    }

    function renderHl2Challenge() {
        if (!hl2Challenge || !hl2GameArea) return;
        const type = hl2Challenge.challenge_type;
        if (hl2Prompt) hl2Prompt.textContent = hl2Challenge.prompt || '';
        setHl2Status('working', `TRIAL ACTIVE: ${hl2Challenge.title || 'PROVE YOURSELF'} — solve it to earn one upload.`);
        hl2GameArea.innerHTML = '';

        if (type === 'hev_math') {
            const q = (hl2Challenge.payload && hl2Challenge.payload.question) || '?';
            const wrap = document.createElement('div');
            wrap.className = 'hl2-math-row';
            wrap.innerHTML = `<span class="hl2-math-q">⚡ ${escapeHtml(q)} = ?</span>`;
            const input = document.createElement('input');
            input.id = 'hl2MathAnswer';
            input.className = 'hl2-input';
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('autocomplete', 'off');
            input.placeholder = '0';
            input.addEventListener('keydown', (e) => { if (e.key === 'Enter') verifyHl2Solution(); });
            wrap.appendChild(input);
            hl2GameArea.appendChild(wrap);
            if (hl2VerifyBtn) hl2VerifyBtn.disabled = false;
            setTimeout(() => input.focus(), 50);
        } else if (type === 'lambda_memory') {
            const seq = (hl2Challenge.payload && hl2Challenge.payload.sequence) || [];
            const info = document.createElement('p');
            info.className = 'hl2-prompt';
            info.textContent = `Memorize the flashing ${seq.length}-glyph transmission, then click the glyphs in order.`;
            hl2GameArea.appendChild(info);
            const grid = document.createElement('div');
            grid.className = 'hl2-mem-grid';
            const seen = [...new Set(seq)];
            seen.forEach(id => {
                const m = symbolMeta(id);
                const tile = document.createElement('div');
                tile.className = 'hl2-tile';
                tile.dataset.symbol = id;
                tile.innerHTML = `<span class="hl2-icon">${escapeHtml(m.icon)}</span><span class="hl2-cap">${escapeHtml(m.label)}</span>`;
                tile.addEventListener('click', () => {
                    window._hl2MemInput = window._hl2MemInput || [];
                    window._hl2MemInput.push(id);
                    tile.classList.add('picked');
                    updateHl2MemProgress();
                    setTimeout(() => tile.classList.remove('picked'), 350);
                    if (window._hl2MemInput.length >= seq.length && hl2VerifyBtn) hl2VerifyBtn.disabled = false;
                });
                grid.appendChild(tile);
            });
            hl2GameArea.appendChild(grid);
            const prog = document.createElement('div');
            prog.id = 'hl2MemProgress';
            prog.className = 'hl2-seq-progress';
            hl2GameArea.appendChild(prog);
            const replay = document.createElement('button');
            replay.type = 'button';
            replay.className = 'hl2-replay-btn';
            replay.textContent = '↻ Replay transmission';
            replay.addEventListener('click', () => flashHl2Sequence(seq));
            hl2GameArea.appendChild(replay);
            window._hl2MemInput = [];
            updateHl2MemProgress();
            if (hl2VerifyBtn) hl2VerifyBtn.disabled = true;
            flashHl2Sequence(seq);
        } else if (type === 'headcrab_sweep') {
            const gridData = (hl2Challenge.payload && hl2Challenge.payload.grid) || [];
            const targetCount = (hl2Challenge.payload && hl2Challenge.payload.target_count) || 0;
            const grid = document.createElement('div');
            grid.className = 'hl2-sweep-grid';
            window._hl2SweepPicked = new Set();
            gridData.forEach((symId, idx) => {
                const m = symbolMeta(symId);
                const tile = document.createElement('div');
                tile.className = 'hl2-tile';
                tile.dataset.idx = String(idx);
                tile.title = `Sector ${idx + 1}`;
                tile.innerHTML = `<span class="hl2-icon">${escapeHtml(m.icon)}</span><span class="hl2-cap">SEC ${idx + 1}</span>`;
                tile.addEventListener('click', () => {
                    const i = Number(tile.dataset.idx);
                    if (window._hl2SweepPicked.has(i)) {
                        window._hl2SweepPicked.delete(i);
                        tile.classList.remove('picked');
                    } else {
                        window._hl2SweepPicked.add(i);
                        tile.classList.add('picked');
                    }
                    if (hl2VerifyBtn) hl2VerifyBtn.disabled = window._hl2SweepPicked.size === 0;
                });
                grid.appendChild(tile);
            });
            hl2GameArea.appendChild(grid);
            const note = document.createElement('div');
            note.className = 'hl2-seq-progress';
            note.textContent = `Tap every matching tile (${targetCount} hostiles). Tiles stay dark — trust your eyes, not the Combine.`;
            hl2GameArea.appendChild(note);
            if (hl2VerifyBtn) hl2VerifyBtn.disabled = true;
        }
    }

    function getHl2MemInput() { return window._hl2MemInput || []; }

    function updateHl2MemProgress() {
        const el = document.getElementById('hl2MemProgress');
        const seq = (hl2Challenge && hl2Challenge.payload && hl2Challenge.payload.sequence) || [];
        const cur = getHl2MemInput();
        if (el) el.textContent = cur.length ? `Input ${cur.length}/${seq.length}: ${cur.join(' → ')}` : `Awaiting input (0/${seq.length})…`;
        const undo = document.getElementById('hl2MemUndo');
        if (!undo && hl2GameArea) {
            const b = document.createElement('button');
            b.type = 'button'; b.id = 'hl2MemUndo'; b.className = 'hl2-replay-btn'; b.textContent = '⌫ Undo last';
            b.addEventListener('click', () => { (window._hl2MemInput || []).pop(); updateHl2MemProgress(); });
            hl2GameArea.appendChild(b);
        }
    }

    function flashHl2Sequence(seq) {
        window._hl2MemInput = [];
        updateHl2MemProgress();
        if (hl2VerifyBtn) hl2VerifyBtn.disabled = true;
        const tiles = [...hl2GameArea.querySelectorAll('.hl2-tile')];
        setHl2Status('working', '📡 TRANSMISSION INCOMING — watch closely…');
        seq.forEach((id, step) => {
            setTimeout(() => {
                const tile = tiles.find(t => t.dataset.symbol === id);
                if (tile) {
                    tile.classList.add('lit');
                    setTimeout(() => tile.classList.remove('lit'), 450);
                }
                if (step === seq.length - 1) {
                    setTimeout(() => setHl2Status('working', 'TRANSMISSION ENDS — repeat the sequence.'), 500);
                }
            }, 650 * (step + 1));
        });
    }

    // Memory tile clicks push here (delegated via render closure)
    Object.defineProperty(window, 'hl2MemInput', {
        get: getHl2MemInput,
        set: (v) => { window._hl2MemInput = v; }
    });

    async function verifyHl2Solution() {
        if (!hl2Challenge) {
            showToast('Initiate the security check first.', 'error');
            return;
        }
        const type = hl2Challenge.challenge_type;
        let solution = {};
        if (type === 'hev_math') {
            const inp = document.getElementById('hl2MathAnswer');
            const val = (inp && inp.value || '').trim();
            if (!val) { showToast('Enter the power value first.', 'error'); return; }
            solution = { answer: val };
        } else if (type === 'lambda_memory') {
            const cur = getHl2MemInput();
            const need = ((hl2Challenge.payload && hl2Challenge.payload.length) || 0);
            if (cur.length !== need) { showToast(`Repeat all ${need} glyphs before submitting.`, 'error'); return; }
            solution = { sequence: cur };
        } else if (type === 'headcrab_sweep') {
            const picked = [...(window._hl2SweepPicked || [])];
            if (!picked.length) { showToast('Select at least one sector.', 'error'); return; }
            solution = { cells: picked };
        }
        if (hl2VerifyBtn) { hl2VerifyBtn.disabled = true; hl2VerifyBtn.textContent = '… VERIFYING …'; }
        setHl2Status('working', 'VERIFYING WITH OVERWATCH…');
        try {
            const res = await fetch('/api/upload-challenge/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ challenge_id: hl2Challenge.challenge_id, solution })
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.success && data.upload_token) {
                hl2UploadToken = data.upload_token;
                hl2ClearedFileKey = currentFileKey();
                setHl2Status('granted', '✅ CLEARANCE GRANTED — one file upload authorized. Welcome to Black Mesa.');
                showToast('Clearance granted — upload unlocked for this file.');
                refreshUploadButton();
                if (!selectedFileBytes) showToast('Clearance held — now pick your audio file.', 'error');
            } else {
                setHl2Status('lock', '❌ ' + (data.error || 'Wrong solution.'));
                showToast(data.error || 'Wrong solution.', 'error');
                if (data.error && /new security check/i.test(data.error)) {
                    hl2Challenge = null;
                    if (hl2GameArea) hl2GameArea.innerHTML = '';
                }
            }
        } catch (err) {
            setHl2Status('lock', 'VERIFY FAILED: network error.');
            showToast('Network error verifying solution.', 'error');
        } finally {
            if (hl2VerifyBtn) { hl2VerifyBtn.disabled = false; hl2VerifyBtn.textContent = '✔ Submit Solution'; }
            refreshUploadButton();
        }
    }
});
