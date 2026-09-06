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
            setHl2Status('lock', 'New file detected — play a fresh mission to unlock upload.');
            // Convenience: auto-summon a new mission for the new file.
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
            showToast('Complete the Black Mesa mission first — one pass per file.', 'error');
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
                stopHl2Game();
                if (hl2GameArea) hl2GameArea.innerHTML = '';
                if (hl2Prompt) hl2Prompt.textContent = 'Clearance spent. Start a new mission for your next file, citizen.';
                setHl2Status('lock', 'CLEARANCE SPENT — one pass per file. New upload needs a new check.');
                refreshUploadButton();
                await fetchSoundboard();
            } else {
                if (res.status === 403 && data.minigame_required) {
                    showToast(data.error || 'Mission clearance required.', 'error');
                    resetHl2Clearance('LOCKDOWN: clearance rejected — play the mission again.');
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

    // ── Black Mesa: HEADCRAB EXTERMINATION aim-trainer (canvas, mouse) ──
    let hl2Game = null;
    let hl2AudioCtx = null;

    function hl2Beep(freqFrom, freqTo, dur, type, vol) {
        try {
            hl2AudioCtx = hl2AudioCtx || new (window.AudioContext || window.webkitAudioContext)();
            if (hl2AudioCtx.state === 'suspended') hl2AudioCtx.resume();
            const t0 = hl2AudioCtx.currentTime;
            const osc = hl2AudioCtx.createOscillator();
            const gain = hl2AudioCtx.createGain();
            osc.type = type || 'square';
            osc.frequency.setValueAtTime(freqFrom, t0);
            osc.frequency.exponentialRampToValueAtTime(Math.max(1, freqTo), t0 + dur);
            gain.gain.setValueAtTime(vol || 0.08, t0);
            gain.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
            osc.connect(gain);
            gain.connect(hl2AudioCtx.destination);
            osc.start(t0);
            osc.stop(t0 + dur + 0.02);
        } catch (e) {}
    }

    function hl2Sfx(name) {
        if (name === 'shoot') hl2Beep(720, 180, 0.07, 'square', 0.05);
        else if (name === 'hit') hl2Beep(320, 90, 0.12, 'triangle', 0.10);
        else if (name === 'decoy') hl2Beep(150, 70, 0.25, 'sawtooth', 0.10);
        else if (name === 'miss') hl2Beep(240, 200, 0.05, 'square', 0.03);
        else if (name === 'win') {
            hl2Beep(440, 440, 0.12, 'sine', 0.09);
            setTimeout(() => hl2Beep(554, 554, 0.12, 'sine', 0.09), 130);
            setTimeout(() => hl2Beep(659, 659, 0.22, 'sine', 0.09), 260);
        } else if (name === 'lose') {
            hl2Beep(330, 330, 0.15, 'sawtooth', 0.07);
            setTimeout(() => hl2Beep(220, 110, 0.30, 'sawtooth', 0.07), 160);
        }
    }

    function stopHl2Game() {
        if (hl2Game && hl2Game.raf) {
            try { cancelAnimationFrame(hl2Game.raf); } catch (e) {}
        }
        hl2Game = null;
    }

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

    function setupHl2Checkpoint() {
        if (hl2NewChallengeBtn) hl2NewChallengeBtn.addEventListener('click', () => requestHl2Challenge(false));
        if (hl2VerifyBtn) hl2VerifyBtn.addEventListener('click', verifyHl2Solution);
        refreshUploadButton();
    }

    async function requestHl2Challenge(silent) {
        if (!hl2GameArea) return;
        stopHl2Game();
        setHl2Status('working', 'CONTACTING BLACK MESA… generating randomized mission.');
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
            if (!silent) showToast('Could not reach mission control.', 'error');
        }
    }

    function renderHl2Challenge() {
        if (!hl2Challenge || !hl2GameArea) return;
        stopHl2Game();
        if (hl2Challenge.challenge_type !== 'headcrab_aim') {
            if (hl2Prompt) hl2Prompt.textContent = 'Unknown mission type — request a new mission.';
            hl2GameArea.innerHTML = '';
            return;
        }
        if (hl2Prompt) hl2Prompt.textContent = hl2Challenge.prompt || '';
        if (hl2VerifyBtn) hl2VerifyBtn.style.display = 'none';
        if (hl2NewChallengeBtn) hl2NewChallengeBtn.textContent = '↻ New Mission';
        setHl2Status('working', 'MISSION BRIEFING — press START MISSION, then shoot every headcrab.');
        hl2GameArea.innerHTML = '';

        const P = hl2Challenge.payload;
        const hud = document.createElement('div');
        hud.className = 'hl2-hud';
        hud.innerHTML =
            '<span id="hl2HudHits">🎯 0/' + P.required_hits + '</span>' +
            '<span class="hl2-timer-wrap"><span id="hl2HudTime">⏱ ' + P.time_limit_s + 's</span>' +
            '<span class="hl2-timer-bar"><span id="hl2HudTimeBar"></span></span></span>' +
            '<span id="hl2HudLives">❤❤❤</span>';
        const wrap = document.createElement('div');
        wrap.className = 'hl2-canvas-wrap';
        const canvas = document.createElement('canvas');
        canvas.width = P.w;
        canvas.height = P.h;
        canvas.className = 'hl2-game';
        const overlay = document.createElement('div');
        overlay.className = 'hl2-overlay';
        overlay.innerHTML =
            '<div class="hl2-overlay-title">☢ RAVENHOLM OVERRUN</div>' +
            '<div class="hl2-overlay-sub">Neutralize <b>' + P.required_hits + '</b> headcrabs in ' +
            '<b>' + P.time_limit_s + 's</b>.<br>Aim with the mouse, click to shoot.<br>' +
            'Civilians, scanners &amp; vortigaunts are friendly — friendly fire costs a life (3 lives).</div>' +
            '<button type="button" class="hl2-btn hl2-btn-primary hl2-start-btn">▶ Start Mission</button>';
        wrap.appendChild(canvas);
        wrap.appendChild(overlay);
        hl2GameArea.appendChild(hud);
        hl2GameArea.appendChild(wrap);

        const G = hl2Game = {
            canvas: canvas, ctx: canvas.getContext('2d'), overlay: overlay, P: P,
            state: 'ready', raf: 0, elapsed: 0, lastTs: 0,
            mouse: { x: -99, y: -99, inside: false },
            ents: [], particles: [],
            hits: 0, lives: P.lives || 3, timeLeft: P.time_limit_s,
            startPerf: 0, events: [], result: null,
            shake: 0, flash: 0, skyline: []
        };
        P.targets.forEach(function (t) {
            G.ents.push({ tid: t.tid, kind: 'target', icon: t.icon, bx: t.x, by: t.y,
                r: t.r, amp: t.amp, speed: t.speed, phase: t.phase, alive: true, x: t.x, y: t.y });
        });
        P.decoys.forEach(function (d) {
            G.ents.push({ tid: d.tid, kind: 'decoy', icon: d.icon, label: d.label, bx: d.x, by: d.y,
                r: d.r, amp: d.amp, speed: d.speed, phase: d.phase, alive: true, x: d.x, y: d.y });
        });
        G.ents.sort(function () { return Math.random() - 0.5; });
        for (let i = 0; i < 14; i++) {
            G.skyline.push({ x: (P.w / 14) * i, w: P.w / 14 - 2, h: 20 + Math.random() * 55 });
        }

        function toGame(ev) {
            const r = canvas.getBoundingClientRect();
            const cx = ev.touches ? ev.touches[0].clientX : ev.clientX;
            const cy = ev.touches ? ev.touches[0].clientY : ev.clientY;
            return { x: (cx - r.left) * canvas.width / r.width, y: (cy - r.top) * canvas.height / r.height };
        }
        canvas.addEventListener('mousemove', function (e) {
            const p = toGame(e); G.mouse.x = p.x; G.mouse.y = p.y; G.mouse.inside = true;
        });
        canvas.addEventListener('mouseleave', function () { G.mouse.inside = false; });
        canvas.addEventListener('mousedown', function (e) { e.preventDefault(); const p = toGame(e); hl2Shoot(p.x, p.y); });
        canvas.addEventListener('touchstart', function (e) {
            e.preventDefault();
            const p = toGame(e); G.mouse.x = p.x; G.mouse.y = p.y; G.mouse.inside = true;
            hl2Shoot(p.x, p.y);
        }, { passive: false });
        canvas.addEventListener('contextmenu', function (e) { e.preventDefault(); });
        overlay.querySelector('.hl2-start-btn').addEventListener('click', function () {
            hl2Sfx('shoot');
            overlay.classList.add('hidden');
            G.state = 'playing';
            G.startPerf = performance.now();
            G.lastTs = 0;
            setHl2Status('working', '⚔ MISSION LIVE — neutralize every headcrab!');
        });

        updateHl2Hud();
        G.raf = requestAnimationFrame(hl2Loop);
    }

    function updateHl2Hud() {
        if (!hl2Game) return;
        const G = hl2Game, P = G.P;
        const hits = document.getElementById('hl2HudHits');
        const time = document.getElementById('hl2HudTime');
        const bar = document.getElementById('hl2HudTimeBar');
        const lives = document.getElementById('hl2HudLives');
        if (hits) hits.textContent = '🎯 ' + G.hits + '/' + P.required_hits;
        if (time) time.textContent = '⏱ ' + Math.ceil(G.timeLeft) + 's';
        if (bar) {
            const frac = Math.max(0, G.timeLeft / P.time_limit_s);
            bar.style.width = (frac * 100).toFixed(1) + '%';
            bar.style.background = frac < 0.25 ? '#ff3b30' : '#ffb340';
        }
        if (lives) lives.textContent = '❤'.repeat(G.lives) + '🖤'.repeat(Math.max(0, (P.lives || 3) - G.lives));
    }

    function hl2Burst(x, y, color, n, spd) {
        if (!hl2Game) return;
        for (let i = 0; i < (n || 10); i++) {
            const a = Math.random() * Math.PI * 2;
            const v = (0.3 + Math.random() * 0.7) * (spd || 90);
            hl2Game.particles.push({ x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 30,
                life: 0.5 + Math.random() * 0.4, age: 0, color: color, size: 1.5 + Math.random() * 2.5 });
        }
    }

    function hl2Shoot(x, y) {
        const G = hl2Game;
        if (!G || G.state !== 'playing') return;
        hl2Sfx('shoot');
        hl2Burst(x, y, '#ffd76a', 5, 60);
        let best = null, bestD = Infinity;
        for (let i = G.ents.length - 1; i >= 0; i--) {
            const e = G.ents[i];
            if (!e.alive) continue;
            const d = Math.hypot(e.x - x, e.y - y);
            if (d <= e.r && d < bestD) { best = e; bestD = d; }
        }
        if (!best) { hl2Sfx('miss'); return; }
        const nowMs = performance.now() - G.startPerf;
        if (best.kind === 'target') {
            best.alive = false;
            G.hits++;
            G.events.push({ tid: best.tid, t: Math.round(nowMs) });
            hl2Sfx('hit');
            hl2Burst(best.x, best.y, '#7CFC00', 14, 110);
            hl2Burst(best.x, best.y, '#ff3b30', 6, 70);
            updateHl2Hud();
            if (G.hits >= G.P.required_hits) hl2Win();
        } else {
            G.lives--;
            G.flash = 1;
            G.shake = 7;
            hl2Sfx('decoy');
            hl2Burst(best.x, best.y, '#ff3b30', 12, 90);
            updateHl2Hud();
            if (G.lives <= 0) hl2Lose('FRIENDLY FIRE — you harmed the innocent. The mission is scrubbed.');
            else showToast('Friendly fire! ' + G.lives + ' ' + (G.lives === 1 ? 'life' : 'lives') + ' left.', 'error');
        }
    }

    function hl2Win() {
        const G = hl2Game;
        if (!G || G.state !== 'playing') return;
        G.state = 'won';
        const durationMs = Math.round(performance.now() - G.startPerf);
        G.result = {
            hits: G.events.map(function (e) { return e.tid; }),
            events: G.events.slice(),
            duration_ms: durationMs
        };
        hl2Sfx('win');
        setHl2Status('working', '✅ SECTOR CLEAR — transmitting after-action report…');
        G.overlay.innerHTML = '<div class="hl2-overlay-title" style="color:#35e065">✔ SECTOR CLEAR</div>' +
            '<div class="hl2-overlay-sub">All headcrabs neutralized in ' + (durationMs / 1000).toFixed(1) + 's.<br>Transmitting report to Overwatch…</div>';
        G.overlay.classList.remove('hidden');
        setTimeout(function () { verifyHl2Solution(); }, 800);
    }

    function hl2Lose(reason) {
        const G = hl2Game;
        if (!G || G.state !== 'playing') return;
        G.state = 'lost';
        hl2Sfx('lose');
        setHl2Status('lock', '❌ MISSION FAILED — ' + reason + ' Request a new mission to retry.');
        G.overlay.innerHTML = '<div class="hl2-overlay-title" style="color:#ff3b30">✖ MISSION FAILED</div>' +
            '<div class="hl2-overlay-sub">' + escapeHtml(reason) + '<br>Each attempt needs a fresh, randomized mission.</div>' +
            '<button type="button" class="hl2-btn hl2-btn-primary hl2-start-btn">↻ Retry Mission</button>';
        G.overlay.classList.remove('hidden');
        G.overlay.querySelector('.hl2-start-btn').addEventListener('click', function () { requestHl2Challenge(true); });
    }

    function hl2DrawBackdrop(ctx, G) {
        const P = G.P, W = P.w, H = P.h;
        const palettes = {
            city17: ['#2b1a3a', '#e8722a', '#1a0f24'],
            canals: ['#0b2b2e', '#3fb8a8', '#071a1c'],
            citadel: ['#0d1b3d', '#7fa8ff', '#070d20']
        };
        const pal = palettes[P.backdrop] || palettes.city17;
        const grad = ctx.createLinearGradient(0, 0, 0, H);
        grad.addColorStop(0, '#050508');
        grad.addColorStop(0.55, pal[0]);
        grad.addColorStop(1, pal[2]);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        G.skyline.forEach(function (b) { ctx.fillRect(b.x, H - 44 - b.h, b.w, b.h); });
        if (P.backdrop === 'citadel') {
            ctx.fillStyle = 'rgba(127,168,255,0.25)';
            ctx.fillRect(W / 2 - 14, 0, 28, H - 40);
        }
        ctx.fillStyle = 'rgba(0,0,0,0.65)';
        ctx.fillRect(0, H - 44, W, 44);
        ctx.fillStyle = 'rgba(255,255,255,0.06)';
        ctx.fillRect(0, H - 44, W, 2);
        ctx.save();
        ctx.globalAlpha = 0.10;
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 120px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('λ', W / 2, H / 2);
        ctx.restore();
    }

    function hl2Loop(ts) {
        const G = hl2Game;
        if (!G) return;
        if (!G.lastTs) G.lastTs = ts;
        const dt = Math.min(0.05, Math.max(0.001, (ts - G.lastTs) / 1000));
        G.lastTs = ts;
        G.elapsed += dt;
        if (G.state === 'playing') {
            G.timeLeft -= dt;
            if (G.timeLeft <= 0) {
                G.timeLeft = 0;
                updateHl2Hud();
                hl2Lose('TIME UP — headcrabs overran the sector.');
            } else {
                updateHl2Hud();
            }
        }
        const ctx = G.ctx, P = G.P;
        ctx.save();
        if (G.shake > 0.2) {
            ctx.translate((Math.random() - 0.5) * G.shake, (Math.random() - 0.5) * G.shake);
            G.shake *= 0.88;
        }
        hl2DrawBackdrop(ctx, G);
        G.ents.forEach(function (e) {
            e.x = e.bx + Math.cos(G.elapsed * e.speed + e.phase) * e.amp;
            e.y = e.by + Math.sin(G.elapsed * e.speed * 1.3 + e.phase) * e.amp * 0.7;
            if (!e.alive) return;
            ctx.beginPath();
            ctx.ellipse(e.x, e.y + e.r * 0.9, e.r * 0.9, e.r * 0.35, 0, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(0,0,0,0.4)';
            ctx.fill();
            ctx.beginPath();
            ctx.arc(e.x, e.y, e.r + 3, 0, Math.PI * 2);
            ctx.strokeStyle = e.kind === 'target' ? 'rgba(255,80,60,0.85)' : 'rgba(120,200,255,0.7)';
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.font = (e.r * 2 - 4) + 'px serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(e.icon, e.x, e.y + 1);
        });
        G.particles = G.particles.filter(function (p) { return p.age < p.life; });
        G.particles.forEach(function (p) {
            p.age += dt;
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            p.vy += 160 * dt;
            ctx.globalAlpha = Math.max(0, 1 - p.age / p.life);
            ctx.fillStyle = p.color;
            ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
            ctx.globalAlpha = 1;
        });
        if (G.mouse.inside && G.state === 'playing') {
            const mx = G.mouse.x, my = G.mouse.y;
            ctx.strokeStyle = '#ffb340';
            ctx.lineWidth = 1.5;
            ctx.beginPath(); ctx.arc(mx, my, 10, 0, Math.PI * 2); ctx.stroke();
            ctx.beginPath();
            [[-16, 0, -6, 0], [6, 0, 16, 0], [0, -16, 0, -6], [0, 6, 0, 16]].forEach(function (l) {
                ctx.moveTo(mx + l[0], my + l[1]); ctx.lineTo(mx + l[2], my + l[3]);
            });
            ctx.stroke();
            ctx.fillStyle = '#ffb340';
            ctx.fillRect(mx - 1, my - 1, 2, 2);
        }
        if (G.flash > 0.02) {
            ctx.fillStyle = 'rgba(255,40,30,' + (G.flash * 0.28).toFixed(3) + ')';
            ctx.fillRect(-10, -10, P.w + 20, P.h + 20);
            G.flash *= 0.9;
        }
        ctx.restore();
        G.raf = requestAnimationFrame(hl2Loop);
    }

    async function verifyHl2Solution() {
        if (!hl2Challenge) {
            showToast('Start the mission first.', 'error');
            return;
        }
        if (hl2Challenge.challenge_type !== 'headcrab_aim' || !hl2Game || !hl2Game.result) {
            showToast('Finish the mission first — neutralize every headcrab.', 'error');
            return;
        }
        const solution = {
            hits: hl2Game.result.hits,
            events: hl2Game.result.events,
            duration_ms: hl2Game.result.duration_ms
        };
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
                setHl2Status('lock', '❌ ' + (data.error || 'Report rejected.'));
                showToast(data.error || 'Report rejected.', 'error');
                if (data.error && /new (mission|one)/i.test(data.error)) {
                    hl2Challenge = null;
                    stopHl2Game();
                    if (hl2GameArea) hl2GameArea.innerHTML = '';
                }
            }
        } catch (err) {
            setHl2Status('lock', 'VERIFY FAILED: network error.');
            showToast('Network error verifying solution.', 'error');
        } finally {
            refreshUploadButton();
        }
    }
});
