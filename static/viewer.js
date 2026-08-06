// Twitch TTS Viewer Hub - Windows 95 Soundboard Main Edition Logic

document.addEventListener('DOMContentLoaded', () => {
    // State Stores
    let commandsData = [];
    let soundboardList = [];
    let activeChannel = '';
    let selectedFileBytes = null;
    let selectedFileName = '';

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
        
        // Setup local audio preview player
        const objectUrl = URL.createObjectURL(file);
        if (localFilePreviewPlayer) localFilePreviewPlayer.src = objectUrl;

        if (selectedFileInfo) selectedFileInfo.classList.remove('hidden');

        // Read bytes as Base64 for submission
        const reader = new FileReader();
        reader.onload = function(e) {
            selectedFileBytes = e.target.result;
            if (uploadSubmitBtn) uploadSubmitBtn.disabled = false;
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

        if (uploadSubmitBtn) {
            uploadSubmitBtn.disabled = true;
            uploadSubmitBtn.textContent = '⏳ VALIDATING & UPLOADING...';
        }

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
                if (selectedFileInfo) selectedFileInfo.classList.add('hidden');
                await fetchSoundboard();
            } else {
                showToast(data.error || 'Upload failed validation.', 'error');
            }
        } catch (err) {
            showToast('Network error during upload request.', 'error');
        } finally {
            if (uploadSubmitBtn) {
                uploadSubmitBtn.disabled = false;
                uploadSubmitBtn.textContent = '💾 Upload & Register Sound';
            }
        }
    }
});
