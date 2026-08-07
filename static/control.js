/**
 * Streamer Control Portal Frontend JS Application
 * Handles OBS Overlay generation, Twitch Channel monitoring, Soundboard triggers,
 * Audio queue player, Chatter Signature Voices, Stream Death Counter, and Password Protection.
 */

document.addEventListener("DOMContentLoaded", () => {
    // State management
    const state = {
        channels: [],
        activeChannel: "",
        connected: false,
        soundboardEnabled: true,
        sounds: [],
        voices: [],
        userVoices: {},
        ignoredUsers: [],
        counter: 0,
        audioQueue: [],
        isPlayingAudio: false,
        currentAudio: null,
        obsPort: 5001,
        siteDomain: "",
        serverPort: window.location.port || 5000,
        serverHost: window.location.hostname || "localhost",
        authRequired: false,
        authenticated: false,
        chaosMode: false,
        selectedChannel: localStorage.getItem("control_selected_channel") || ""
    };

    // DOM Elements
    const elements = {
        // Password Protection Modal & Lock Button
        authLockModal: document.getElementById("authLockModal"),
        controlPasswordInput: document.getElementById("controlPasswordInput"),
        controlLoginBtn: document.getElementById("controlLoginBtn"),
        controlLoginError: document.getElementById("controlLoginError"),
        portalLockBtn: document.getElementById("portalLockBtn"),
        lockBtnIcon: document.getElementById("lockBtnIcon"),
        lockBtnText: document.getElementById("lockBtnText"),

        // Channel connect & Channel Selector
        statusPill: document.getElementById("statusPill"),
        statusText: document.getElementById("statusText"),
        channelInput: document.getElementById("channelInput"),
        connectBtn: document.getElementById("connectBtn"),
        channelsChips: document.getElementById("channelsChips"),
        controlChannelSelect: document.getElementById("controlChannelSelect"),
        
        // OBS Builder
        obsChannelSelect: document.getElementById("obsChannelSelect"),
        optChan1: document.getElementById("optChan1"),
        optChan2: document.getElementById("optChan2"),
        posBtns: document.querySelectorAll(".pos-btn"),
        obsVolume: document.getElementById("obsVolume"),
        volumeVal: document.getElementById("volumeVal"),
        obsFontSize: document.getElementById("obsFontSize"),
        fontSizeVal: document.getElementById("fontSizeVal"),
        obsAutohide: document.getElementById("obsAutohide"),
        obsChime: document.getElementById("obsChime"),
        obsGeneratedUrl: document.getElementById("obsGeneratedUrl"),
        copyUrlBtn: document.getElementById("copyUrlBtn"),
        launchObsBtn: document.getElementById("launchObsBtn"),
        simulatedOverlay: document.getElementById("simulatedOverlay"),
        simCardText: document.getElementById("simCardText"),

        // LUA Generator
        luaGeneratedUrl: document.getElementById("luaGeneratedUrl"),
        downloadLuaBtn: document.getElementById("downloadLuaBtn"),
        copyLuaUrlBtn: document.getElementById("copyLuaUrlBtn"),
        luaChannelHint: document.getElementById("luaChannelHint"),
        
        // Soundboard
        soundboardMasterToggle: document.getElementById("soundboardMasterToggle"),
        soundSearch: document.getElementById("soundSearch"),
        soundboardGrid: document.getElementById("soundboardGrid"),
        
        // Audio Player & Log
        eqVisualizer: document.getElementById("eqVisualizer"),
        spectrumCanvas: document.getElementById("spectrumCanvas"),
        queueBadge: document.getElementById("queueBadge"),
        currentSpeaker: document.getElementById("currentSpeaker"),
        currentText: document.getElementById("currentText"),
        chaosToggleBtn: document.getElementById("chaosToggleBtn"),
        chaosBtnText: document.getElementById("chaosBtnText"),
        skipAudioBtn: document.getElementById("skipAudioBtn"),
        clearQueueBtn: document.getElementById("clearQueueBtn"),
        chatLogList: document.getElementById("chatLogList"),
        clearChatLogBtn: document.getElementById("clearChatLogBtn"),
        
        // TTS Test
        testTextInput: document.getElementById("testTextInput"),
        testVoiceSelect: document.getElementById("testVoiceSelect"),
        test8dToggle: document.getElementById("test8dToggle"),
        testSpeakBtn: document.getElementById("testSpeakBtn"),
        
        // User Voices
        chatterUserVal: document.getElementById("chatterUserVal"),
        chatterVoiceVal: document.getElementById("chatterVoiceVal"),
        chatterLockVal: document.getElementById("chatterLockVal"),
        addVoiceBtn: document.getElementById("addVoiceBtn"),
        userVoicesTableBody: document.getElementById("userVoicesTableBody"),
        
        // Ignored Users
        ignoredUserVal: document.getElementById("ignoredUserVal"),
        addIgnoredUserBtn: document.getElementById("addIgnoredUserBtn"),
        clearIgnoredUsersBtn: document.getElementById("clearIgnoredUsersBtn"),
        ignoredUsersTableBody: document.getElementById("ignoredUsersTableBody"),
        
        // Death Counter
        counterNumber: document.getElementById("counterNumber"),
        countIncBtn: document.getElementById("countIncBtn"),
        countDecBtn: document.getElementById("countDecBtn"),
        countResetBtn: document.getElementById("countResetBtn"),
        testBibleVerseBtn: document.getElementById("testBibleVerseBtn"),

        // Preferences & Audio Settings
        prefEnable8D: document.getElementById("prefEnable8D"),
        pref8dSpeed: document.getElementById("pref8dSpeed"),
        pref8dSpeedVal: document.getElementById("pref8dSpeedVal"),
        prefChatResponses: document.getElementById("prefChatResponses"),
        prefKillCounter: document.getElementById("prefKillCounter"),
        prefChaosMode: document.getElementById("prefChaosMode"),
        prefCooldown: document.getElementById("prefCooldown"),
        prefCooldownVal: document.getElementById("prefCooldownVal"),
        
        toastContainer: document.getElementById("toastContainer")
    };

    // Current OBS Position Selection
    let selectedPosition = "bottom-right";

    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // --- Toast Notifications ---
    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        elements.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(100%)";
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // --- Helper Fetch wrapper with Auth Token Injection ---
    async function apiRequest(url, options = {}) {
        try {
            const token = localStorage.getItem("admin_token") || "";
            const headers = { "Content-Type": "application/json", ...options.headers };
            if (token) {
                headers["X-Admin-Token"] = token;
                headers["Authorization"] = `Bearer ${token}`;
            }

            const resp = await fetch(url, { ...options, headers });
            
            // Handle HTTP 401 Unauthorized
            if (resp.status === 401) {
                const data = await resp.json().catch(() => ({}));
                if (data.auth_required) {
                    state.authRequired = true;
                    state.authenticated = false;
                    showAuthLockModal();
                }
                throw new Error(data.error || "Authentication required");
            }

            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
            return data;
        } catch (err) {
            console.error(`API Request Error [${url}]:`, err);
            if (!url.includes("/api/auth/status") && !url.includes("/api/auth/login")) {
                showToast(err.message, "error");
            }
            throw err;
        }
    }

    // --- Password Protection Logic ---
    async function checkAuthStatus() {
        try {
            const authStatus = await apiRequest("/api/auth/status");
            state.userAuthRequired = authStatus.user_auth_required || false;
            state.authRequired = authStatus.auth_required || false;
            state.authenticated = authStatus.authenticated || false;

            if (state.userAuthRequired && !state.authenticated) {
                showAuthLockModal();
                elements.portalLockBtn.classList.remove("unlocked");
                elements.lockBtnIcon.className = "material-symbols-outlined";
                elements.lockBtnIcon.textContent = "lock";
                elements.lockBtnText.textContent = "Locked";
            } else if (state.userAuthRequired && state.authenticated) {
                hideAuthLockModal();
                elements.portalLockBtn.classList.add("unlocked");
                elements.lockBtnIcon.className = "material-symbols-outlined";
                elements.lockBtnIcon.textContent = "lock_open";
                elements.lockBtnText.textContent = "Lock Portal";
            } else {
                hideAuthLockModal();
                elements.portalLockBtn.classList.remove("unlocked");
                elements.lockBtnIcon.className = "material-symbols-outlined";
                elements.lockBtnIcon.textContent = "public";
                elements.lockBtnText.textContent = "Public Mode";
            }
        } catch (e) {
            console.warn("Could not fetch auth status", e);
        }
    }

    function showAuthLockModal() {
        if (elements.authLockModal) {
            elements.authLockModal.classList.remove("hidden");
        }
        if (elements.controlLoginError) {
            elements.controlLoginError.classList.add("hidden");
        }
    }

    function hideAuthLockModal() {
        if (elements.authLockModal) {
            elements.authLockModal.classList.add("hidden");
        }
    }

    async function performLogin() {
        const password = elements.controlPasswordInput.value.trim();
        if (!password) {
            showLoginError("Please enter Streamer Password");
            return;
        }

        try {
            elements.controlLoginBtn.disabled = true;
            elements.controlLoginBtn.textContent = "Verifying...";
            
            const res = await apiRequest("/api/auth/login", {
                method: "POST",
                body: JSON.stringify({ password })
            });

            if (res.token) {
                localStorage.setItem("admin_token", res.token);
                state.authenticated = true;
                hideAuthLockModal();
                showToast("Control Portal Unlocked!", "success");
                elements.controlPasswordInput.value = "";
                await checkAuthStatus();
                loadInitialStatus();
            }
        } catch (e) {
            showLoginError(e.message || "Invalid Streamer Password");
        } finally {
            elements.controlLoginBtn.disabled = false;
            elements.controlLoginBtn.innerHTML = "🔓 Unlock";
        }
    }

    // Win95 Tab Strip Handler
    const tabBtns = document.querySelectorAll(".win95-tab");
    const tabContents = document.querySelectorAll(".tab-content");
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            btn.classList.add("active");
            const targetElement = document.getElementById(targetTab);
            if (targetElement) targetElement.classList.add("active");
        });
    });

    function showLoginError(msg) {
        if (elements.controlLoginError) {
            elements.controlLoginError.textContent = msg;
            elements.controlLoginError.classList.remove("hidden");
        }
    }

    elements.controlLoginBtn.addEventListener("click", performLogin);
    elements.controlPasswordInput.addEventListener("keyup", (e) => {
        if (e.key === "Enter") performLogin();
    });

    elements.portalLockBtn.addEventListener("click", async () => {
        if (!state.userAuthRequired) {
            showToast("Streamer password protection is not configured in server settings.", "info");
            return;
        }

        if (state.authenticated) {
            try {
                await apiRequest("/api/auth/logout", { method: "POST" });
            } catch (e) {}
            localStorage.removeItem("admin_token");
            state.authenticated = false;
            showAuthLockModal();
            elements.portalLockBtn.classList.remove("unlocked");
            elements.lockBtnIcon.className = "material-symbols-outlined";
            elements.lockBtnIcon.textContent = "lock";
            elements.lockBtnText.textContent = "Locked";
            showToast("Control Portal Locked", "info");
        } else {
            showAuthLockModal();
        }
    });

    // --- Load Initial Application Status ---
    async function loadInitialStatus() {
        try {
            const status = await apiRequest("/api/status");
            updateStatusUI(status);
        } catch (e) {
            console.warn("Could not load initial status", e);
        }

        try {
            const voicesData = await apiRequest("/api/voices");
            state.voices = Array.isArray(voicesData) ? voicesData : (voicesData.voices || []);
            populateVoiceDropdowns();
        } catch (e) {
            console.warn("Could not load TTS voices list", e);
        }

        try {
            loadSoundboard();
        } catch (e) {
            console.warn("Could not load soundboard", e);
        }

        try {
            loadUserVoices();
        } catch (e) {
            console.warn("Could not load user voices", e);
        }

        try {
            loadIgnoredUsers();
        } catch (e) {
            console.warn("Could not load ignored users", e);
        }

        try {
            loadKillCounter();
        } catch (e) {
            console.warn("Could not load counter", e);
        }
    }

    function updateStatusUI(status) {
        if (!status) return;
        state.connected = status.connected !== undefined ? status.connected : (status.twitch_connected || false);
        state.channels = status.channels || [];
        if (status.config) {
            const domainVal = status.config.site_domain || status.config.public_domain || status.config.domain;
            if (domainVal) {
                state.siteDomain = String(domainVal).trim();
            }
            const portVal = status.config.public_server_port || status.config.obs_server_port;
            if (portVal) {
                state.obsPort = portVal;
            }
            if (status.config.enable_chaos_mode !== undefined) {
                state.chaosMode = !!status.config.enable_chaos_mode;
                updateChaosUI(state.chaosMode);
            }
            if (status.config.ignored_users) {
                state.ignoredUsers = status.config.ignored_users;
                renderIgnoredUsersTable();
            }
        }
        if (status.ignored_users) {
            state.ignoredUsers = status.ignored_users;
            renderIgnoredUsersTable();
        }

        // Status pill
        if (state.connected) {
            elements.statusPill.classList.add("connected");
            elements.statusText.textContent = `Connected (${state.channels.join(", ")})`;
        } else {
            elements.statusPill.classList.remove("connected");
            elements.statusText.textContent = "Disconnected";
        }

        // Channel input
        if (elements.channelInput && state.channels.length > 0 && !elements.channelInput.value) {
            elements.channelInput.value = state.channels.join(", ");
        }

        // Active channel chips
        elements.channelsChips.innerHTML = "";
        if (state.channels.length > 0) {
            state.channels.forEach((ch, idx) => {
                const chip = document.createElement("span");
                chip.className = "chip";
                chip.textContent = `#${ch}`;
                elements.channelsChips.appendChild(chip);
            });
        } else {
            elements.channelsChips.innerHTML = '<span class="chip chip-empty">No Twitch channel connected</span>';
        }

        // Update OBS channel dropdown options
        elements.optChan1.textContent = state.channels[0] ? `Channel 1 (${state.channels[0]})` : "Channel 1";
        elements.optChan1.value = state.channels[0] || "";
        elements.optChan2.textContent = state.channels[1] ? `Channel 2 (${state.channels[1]})` : "Channel 2";
        elements.optChan2.value = state.channels[1] || "";

        // Mandatory Control Channel Selector sync
        const chanSelect = elements.controlChannelSelect;
        if (chanSelect) {
            chanSelect.innerHTML = "";
            if (state.channels.length === 0) {
                const opt = document.createElement("option");
                opt.value = "";
                opt.textContent = "No channels available";
                chanSelect.appendChild(opt);
                state.selectedChannel = "";
            } else {
                state.channels.forEach(ch => {
                    const opt = document.createElement("option");
                    opt.value = ch;
                    opt.textContent = `#${ch}`;
                    chanSelect.appendChild(opt);
                });
                // Mandatory selection: default to active/saved channel or first available channel
                if (!state.selectedChannel || !state.channels.includes(state.selectedChannel)) {
                    state.selectedChannel = state.channels[0];
                }
                chanSelect.value = state.selectedChannel;
            }
            localStorage.setItem("control_selected_channel", state.selectedChannel);
        }

        // Sync preferences settings for selected channel
        if (state.selectedChannel) {
            loadChannelSettings(state.selectedChannel);
        }

        updateObsUrl();
    }

    // Handle mandatory Channel Selector change
    if (elements.controlChannelSelect) {
        elements.controlChannelSelect.addEventListener("change", () => {
            const chosen = elements.controlChannelSelect.value;
            if (chosen) {
                state.selectedChannel = chosen;
                localStorage.setItem("control_selected_channel", chosen);
                if (elements.obsChannelSelect) {
                    elements.obsChannelSelect.value = chosen;
                    updateObsUrl();
                }
                loadChannelSettings(chosen);
                showToast(`Switched active control channel to #${chosen}`, "info");
            }
        });
    }

    async function loadChannelSettings(channel) {
        if (!channel) return;
        try {
            const res = await apiRequest(`/api/control/settings?channel=${encodeURIComponent(channel)}`);
            if (res && res.config) {
                const config = res.config;
                if (elements.prefEnable8D) {
                    elements.prefEnable8D.checked = config.enable_8d_audio !== false;
                    const speedGroup = document.getElementById("pref8dSpeedGroup");
                    if (speedGroup) {
                        speedGroup.style.opacity = elements.prefEnable8D.checked ? "1" : "0.5";
                        speedGroup.style.pointerEvents = elements.prefEnable8D.checked ? "auto" : "none";
                    }
                }
                if (elements.pref8dSpeed) {
                    elements.pref8dSpeed.value = config.effect_8d_speed !== undefined ? config.effect_8d_speed : 0.5;
                    if (elements.pref8dSpeedVal) elements.pref8dSpeedVal.textContent = `${elements.pref8dSpeed.value}s`;
                }
                if (elements.prefChatResponses) {
                    elements.prefChatResponses.checked = config.enable_chat_responses !== false;
                }
                if (elements.prefKillCounter) {
                    elements.prefKillCounter.checked = config.enable_kill_counter !== false;
                }
                if (elements.prefChaosMode) {
                    elements.prefChaosMode.checked = config.enable_chaos_mode !== false;
                    updateChaosUI(!!config.enable_chaos_mode);
                }
                if (elements.prefCooldown) {
                    elements.prefCooldown.value = config.same_user_timeout !== undefined ? config.same_user_timeout : 10;
                    if (elements.prefCooldownVal) elements.prefCooldownVal.textContent = `${elements.prefCooldown.value}s`;
                }
            }
        } catch (e) {
            console.error("Could not load channel settings", e);
        }
    }


    // --- Channel Connect Action ---
    elements.connectBtn.addEventListener("click", async () => {
        const rawInput = elements.channelInput.value.trim();
        if (!rawInput) {
            showToast("Please enter at least one Twitch channel name.", "warning");
            return;
        }

        try {
            elements.connectBtn.disabled = true;
            elements.connectBtn.textContent = "Connecting...";
            const res = await apiRequest("/api/connect", {
                method: "POST",
                body: JSON.stringify({ channel: rawInput })
            });

            showToast(`Connected to Twitch channel(s): ${res.channels.join(", ")}`, "success");
            state.channels = res.channels;
            state.connected = true;
            updateStatusUI({ twitch_connected: true, channels: res.channels });
        } catch (err) {
            showToast("Failed to connect Twitch channels", "error");
        } finally {
            elements.connectBtn.disabled = false;
            elements.connectBtn.innerHTML = "⚡ Connect Chat";
        }
    });

    // --- Interactive OBS Overlay Studio ---
    elements.posBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            elements.posBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedPosition = btn.dataset.pos;
            updateObsUrl();
        });
    });

    elements.obsVolume.addEventListener("input", () => {
        elements.volumeVal.textContent = `${elements.obsVolume.value}%`;
        updateObsUrl();
    });

    elements.obsFontSize.addEventListener("input", () => {
        elements.fontSizeVal.textContent = `${elements.obsFontSize.value}px`;
        updateObsUrl();
    });

    elements.obsChannelSelect.addEventListener("change", updateObsUrl);
    elements.obsAutohide.addEventListener("change", updateObsUrl);
    elements.obsChime.addEventListener("change", updateObsUrl);

    function updateObsUrl() {
        const port = state.obsPort || 5001;
        const domain = (state.siteDomain || "").trim();
        let baseUrl;

        if (domain) {
            let cleanDomain = domain.replace(/\/+$/, '');
            if (cleanDomain.startsWith('http://') || cleanDomain.startsWith('https://')) {
                baseUrl = `${cleanDomain}/obs`;
            } else {
                baseUrl = `https://${cleanDomain}/obs`;
            }
        } else {
            const host = state.serverHost || window.location.hostname || "localhost";
            const protocol = window.location.protocol || "http:";
            if (window.location.port) {
                baseUrl = `${protocol}//${window.location.host}/obs`;
            } else if (port && port !== 80 && port !== 443) {
                baseUrl = `${protocol}//${host}:${port}/obs`;
            } else {
                baseUrl = `${protocol}//${host}/obs`;
            }
        }

        const params = new URLSearchParams();

        if (elements.obsChannelSelect.value) {
            params.set("channel", elements.obsChannelSelect.value);
        }

        if (selectedPosition !== "bottom-right") {
            params.set("position", selectedPosition);
        } else {
            params.set("position", "bottom-right");
        }

        if (elements.obsAutohide.checked) {
            params.set("autohide", "1");
        } else {
            params.set("autohide", "0");
        }

        if (elements.obsVolume.value !== "80") {
            params.set("volume", elements.obsVolume.value);
        }

        if (elements.obsFontSize.value !== "22") {
            params.set("font_size", elements.obsFontSize.value);
        }

        if (!elements.obsChime.checked) {
            params.set("chime", "0");
        }

        const fullUrl = `${baseUrl}?${params.toString()}`;
        elements.obsGeneratedUrl.value = fullUrl;

        // Update LUA script download URL & hint
        let luaBaseUrl;
        const mainPort = state.serverPort || 5000;
        if (domain) {
            let cleanDomain = domain.replace(/\/+$/, '');
            if (cleanDomain.startsWith('http://') || cleanDomain.startsWith('https://')) {
                luaBaseUrl = `${cleanDomain}/darkcounter_obs.lua`;
            } else {
                luaBaseUrl = `https://${cleanDomain}/darkcounter_obs.lua`;
            }
        } else {
            const host = state.serverHost || window.location.hostname || "localhost";
            const protocol = window.location.protocol || "http:";
            if (window.location.port) {
                luaBaseUrl = `${protocol}//${window.location.host}/darkcounter_obs.lua`;
            } else {
                luaBaseUrl = `${protocol}//${host}:${mainPort}/darkcounter_obs.lua`;
            }
        }

        let targetServerUrl;
        if (domain) {
            let cleanDomain = domain.replace(/\/+$/, '');
            targetServerUrl = (cleanDomain.startsWith('http://') || cleanDomain.startsWith('https://')) ? cleanDomain : `https://${cleanDomain}`;
        } else {
            const host = state.serverHost || window.location.hostname || "localhost";
            const protocol = window.location.protocol || "http:";
            if (window.location.port) {
                targetServerUrl = `${protocol}//${window.location.host}`;
            } else {
                targetServerUrl = `${protocol}//${host}:${mainPort}`;
            }
        }

        const luaParams = new URLSearchParams();
        if (targetServerUrl) {
            luaParams.set("server_url", targetServerUrl);
        }
        const selChan = elements.obsChannelSelect.value;
        if (selChan) {
            luaParams.set("channel", selChan);
        }

        const fullLuaUrl = luaParams.toString() ? `${luaBaseUrl}?${luaParams.toString()}` : luaBaseUrl;

        if (elements.luaGeneratedUrl) {
            elements.luaGeneratedUrl.value = fullLuaUrl;
        }
        if (elements.downloadLuaBtn) {
            elements.downloadLuaBtn.href = fullLuaUrl;
        }
        if (elements.luaChannelHint) {
            if (selChan) {
                elements.luaChannelHint.innerHTML = `Selected target channel: <strong style="color:var(--accent-cyan);">${escapeHtml(selChan)}</strong>. Load script into OBS Studio (Tools → Scripts). Deathcounter sounds will only play for channel <strong>${escapeHtml(selChan)}</strong> over everything else.`;
            } else {
                elements.luaChannelHint.innerHTML = `Selected channel: <strong>All Channels</strong>. Load script into OBS Studio (Tools → Scripts). Deathcounter sounds will play over top of everything else as soon as counter goes up.`;
            }
        }

        // Live preview simulation frame update
        elements.simulatedOverlay.className = `simulated-overlay-card pos-${selectedPosition}`;
        elements.simulatedOverlay.style.fontSize = `${elements.obsFontSize.value}px`;
    }

    elements.copyUrlBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(elements.obsGeneratedUrl.value).then(() => {
            showToast("OBS Browser Source URL copied to clipboard!", "success");
        }).catch(() => {
            elements.obsGeneratedUrl.select();
            document.execCommand("copy");
            showToast("OBS Browser Source URL copied!", "success");
        });
    });

    if (elements.copyLuaUrlBtn) {
        elements.copyLuaUrlBtn.addEventListener("click", () => {
            if (elements.luaGeneratedUrl) {
                navigator.clipboard.writeText(elements.luaGeneratedUrl.value).then(() => {
                    showToast("OBS Lua Script Download URL copied to clipboard!", "success");
                }).catch(() => {
                    elements.luaGeneratedUrl.select();
                    document.execCommand("copy");
                    showToast("OBS Lua Script URL copied!", "success");
                });
            }
        });
    }

    elements.launchObsBtn.addEventListener("click", () => {
        window.open(elements.obsGeneratedUrl.value, "_blank");
    });

    // --- Soundboard Panel ---
    async function loadSoundboard() {
        try {
            const sbData = await apiRequest("/api/soundboard");
            state.soundboardEnabled = sbData.enabled !== false;
            state.sounds = sbData.sounds || [];
            elements.soundboardMasterToggle.checked = state.soundboardEnabled;
            renderSoundboardGrid();
        } catch (e) {
            elements.soundboardGrid.innerHTML = '<div class="empty-state">Failed to load soundboard effects</div>';
        }
    }

    elements.soundboardMasterToggle.addEventListener("change", async () => {
        try {
            const enabled = elements.soundboardMasterToggle.checked;
            await apiRequest("/api/soundboard/toggle", {
                method: "POST",
                body: JSON.stringify({ enabled })
            });
            state.soundboardEnabled = enabled;
            showToast(`Soundboard ${enabled ? "Activated" : "Deactivated"}`, "info");
        } catch (e) {
            elements.soundboardMasterToggle.checked = !elements.soundboardMasterToggle.checked;
        }
    });

    elements.soundSearch.addEventListener("input", renderSoundboardGrid);

    function renderSoundboardGrid() {
        const query = elements.soundSearch.value.trim().toLowerCase();
        const filtered = state.sounds.filter(s => s.toLowerCase().includes(query));

        elements.soundboardGrid.innerHTML = "";

        if (filtered.length === 0) {
            elements.soundboardGrid.innerHTML = '<div class="empty-state">No matching sound effects found.</div>';
            return;
        }

        filtered.forEach(soundName => {
            const card = document.createElement("div");
            card.className = "sound-card";
            card.innerHTML = `
                <div class="sound-title"><span class="material-symbols-outlined" style="font-size:16px;">volume_up</span> ${escapeHtml(soundName)}</div>
                <div class="sound-trigger-code">(${escapeHtml(soundName)})</div>
                <div class="sound-actions">
                    <button class="btn btn-small btn-primary trigger-btn" title="Trigger in OBS overlay">
                        <span class="material-symbols-outlined" style="font-size:12px;">play_arrow</span> Overlay
                    </button>
                    <button class="btn btn-small btn-secondary preview-btn" title="Test audio locally in browser">
                        <span class="material-symbols-outlined" style="font-size:12px;">hearing</span> Preview
                    </button>
                </div>
            `;

            // Trigger sound in OBS overlay / playback for selected channel
            card.querySelector(".trigger-btn").addEventListener("click", async () => {
                if (!state.selectedChannel && state.channels.length > 0) {
                    state.selectedChannel = state.channels[0];
                }
                if (!state.selectedChannel) {
                    showToast("Please select a Twitch channel to trigger soundboard audio.", "warning");
                    return;
                }
                try {
                    await apiRequest("/api/soundboard/trigger", {
                        method: "POST",
                        body: JSON.stringify({ sound: soundName, channel: state.selectedChannel })
                    });
                    showToast(`Sound effect '(${soundName})' sent to #${state.selectedChannel} playback!`, "success");
                } catch (e) {
                    showToast(`Failed to trigger sound '${soundName}'`, "error");
                }
            });


            // Preview local audio
            card.querySelector(".preview-btn").addEventListener("click", () => {
                const audio = new Audio(`/api/soundboard/${encodeURIComponent(soundName)}`);
                audio.play().catch(err => showToast("Error playing local preview", "warning"));
            });

            elements.soundboardGrid.appendChild(card);
        });
    }

    // --- TTS Voices & Test Synthesis ---
    function populateVoiceDropdowns() {
        elements.testVoiceSelect.innerHTML = '<option value="">Default Voice</option>';
        elements.chatterVoiceVal.innerHTML = '<option value="">Select Voice...</option>';

        state.voices.forEach(voice => {
            const voiceId = (typeof voice === 'object' && voice !== null) ? (voice.voice_id || voice.name || voice.id) : voice;
            if (!voiceId) return;

            const opt1 = document.createElement("option");
            opt1.value = voiceId;
            opt1.textContent = voiceId;
            elements.testVoiceSelect.appendChild(opt1);

            const opt2 = document.createElement("option");
            opt2.value = voiceId;
            opt2.textContent = voiceId;
            elements.chatterVoiceVal.appendChild(opt2);
        });
    }

    elements.testSpeakBtn.addEventListener("click", async () => {
        let text = elements.testTextInput.value.trim();
        if (!text) {
            showToast("Please enter text to speak.", "warning");
            return;
        }
        if (!state.selectedChannel && state.channels.length > 0) {
            state.selectedChannel = state.channels[0];
        }
        if (!state.selectedChannel) {
            showToast("Please select a Twitch channel to send TTS test messages.", "warning");
            return;
        }

        if (elements.test8dToggle.checked && !text.toLowerCase().includes("{8d}")) {
            text += " {8d}";
        }

        const voice = elements.testVoiceSelect.value || null;

        try {
            elements.testSpeakBtn.disabled = true;
            await apiRequest("/api/tts/test", {
                method: "POST",
                body: JSON.stringify({ text, voice, user: "ControlPortal", channel: state.selectedChannel })
            });
            showToast(`TTS audio test queued for #${state.selectedChannel} playback!`, "success");
            elements.testTextInput.value = "";
        } catch (e) {
            showToast("Failed to queue TTS test", "error");
        } finally {
            elements.testSpeakBtn.disabled = false;
        }
    });


    // --- Chatter Signature Voices Manager ---
    async function loadUserVoices() {
        try {
            const res = await apiRequest("/api/user_voices");
            state.userVoices = res.user_voices || {};
            renderUserVoicesTable();
        } catch (e) {}
    }

    elements.addVoiceBtn.addEventListener("click", async () => {
        const user = elements.chatterUserVal.value.trim().toLowerCase();
        const voice = elements.chatterVoiceVal.value;
        const locked = elements.chatterLockVal ? elements.chatterLockVal.checked : false;
 
        if (!user || !voice) {
            showToast("Please specify both a chatter username and a voice.", "warning");
            return;
        }
 
        try {
            const res = await apiRequest("/api/user_voices/set", {
                method: "POST",
                body: JSON.stringify({ user, voice, locked })
            });
            state.userVoices = res.user_voices || {};
            renderUserVoicesTable();
            showToast(`Assigned voice '${voice}' to @${user}` + (locked ? " (locked)" : ""), "success");
            elements.chatterUserVal.value = "";
            elements.chatterVoiceVal.value = "";
            if (elements.chatterLockVal) elements.chatterLockVal.checked = false;
        } catch (e) {
            showToast("Failed to save chatter voice mapping", "error");
        }
    });

    function renderUserVoicesTable() {
        const tbody = elements.userVoicesTableBody;
        tbody.innerHTML = "";
 
        const entries = Object.entries(state.userVoices);
        if (entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted" style="text-align:center; padding:12px;">No signature voices configured yet.</td></tr>';
            return;
        }
 
        entries.forEach(([user, entry]) => {
            const voiceName = (typeof entry === 'object' && entry !== null) ? (entry.voice || "") : entry;
            const isLocked = (typeof entry === 'object' && entry !== null) ? !!entry.locked : false;

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight:700; color:var(--accent-cyan);">@${escapeHtml(user)}</td>
                <td>
                    <span class="badge badge-purple">${escapeHtml(voiceName)}</span>
                    ${isLocked ? '<span class="material-symbols-outlined" style="font-size:14px; vertical-align:middle; color:var(--warning-amber); margin-left:4px;" title="Voice Locked">lock</span>' : ''}
                </td>
                <td>
                    <button class="btn btn-small btn-danger delete-voice-btn" data-user="${escapeHtml(user)}">
                        <span class="material-symbols-outlined" style="font-size:12px;">delete</span> Delete
                    </button>
                </td>
            `;
 
            tr.querySelector(".delete-voice-btn").addEventListener("click", async () => {
                try {
                    const res = await apiRequest("/api/user_voices/delete", {
                        method: "POST",
                        body: JSON.stringify({ user })
                    });
                    state.userVoices = res.user_voices || {};
                    renderUserVoicesTable();
                    showToast(`Removed custom voice for @${user}`, "info");
                } catch (e) {
                    showToast("Failed to delete voice mapping", "error");
                }
            });
 
            tbody.appendChild(tr);
        });
    }

    // --- Ignored Chatters (Blacklist) Manager ---
    async function loadIgnoredUsers() {
        try {
            const res = await apiRequest("/api/ignored_users");
            state.ignoredUsers = res.ignored_users || [];
            renderIgnoredUsersTable();
        } catch (e) {}
    }

    function renderIgnoredUsersTable() {
        if (!elements.ignoredUsersTableBody) return;
        const tbody = elements.ignoredUsersTableBody;
        tbody.innerHTML = "";

        const list = state.ignoredUsers || [];
        if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; padding:12px; color:#666;">No chatters currently ignored.</td></tr>';
            return;
        }

        list.forEach(user => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight:700; color:var(--warning-amber, #ffab00);">@${escapeHtml(user)}</td>
                <td><span style="background:#d9534f; color:#fff; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:bold;">IGNORED</span></td>
                <td>
                    <button class="win95-btn win95-btn-small unignore-user-btn" data-user="${escapeHtml(user)}">
                        ✅ Remove
                    </button>
                </td>
            `;

            tr.querySelector(".unignore-user-btn").addEventListener("click", async () => {
                try {
                    const res = await apiRequest("/api/ignored_users/delete", {
                        method: "POST",
                        body: JSON.stringify({ user })
                    });
                    state.ignoredUsers = res.ignored_users || [];
                    renderIgnoredUsersTable();
                    showToast(`Removed @${user} from ignored list`, "info");
                } catch (e) {
                    showToast("Failed to remove ignored user", "error");
                }
            });

            tbody.appendChild(tr);
        });
    }

    if (elements.addIgnoredUserBtn) {
        elements.addIgnoredUserBtn.addEventListener("click", async () => {
            const user = elements.ignoredUserVal ? elements.ignoredUserVal.value.trim() : "";
            if (!user) {
                showToast("Please specify a Twitch username to ignore.", "warning");
                return;
            }
            try {
                const res = await apiRequest("/api/ignored_users/add", {
                    method: "POST",
                    body: JSON.stringify({ user })
                });
                state.ignoredUsers = res.ignored_users || [];
                if (elements.ignoredUserVal) elements.ignoredUserVal.value = "";
                renderIgnoredUsersTable();
                showToast(`Added @${user} to ignored list`, "success");
            } catch (e) {
                showToast("Failed to ignore user", "error");
            }
        });
    }

    if (elements.clearIgnoredUsersBtn) {
        elements.clearIgnoredUsersBtn.addEventListener("click", async () => {
            if (!confirm("Are you sure you want to clear all ignored users?")) return;
            try {
                const res = await apiRequest("/api/ignored_users/clear", {
                    method: "POST",
                    body: JSON.stringify({})
                });
                state.ignoredUsers = res.ignored_users || [];
                renderIgnoredUsersTable();
                showToast("Cleared all ignored users", "info");
            } catch (e) {
                showToast("Failed to clear ignored users", "error");
            }
        });
    }

    // --- Stream Death Counter ---
    async function loadKillCounter() {
        try {
            const res = await apiRequest("/api/counter");
            state.counter = res.count || 0;
            elements.counterNumber.textContent = state.counter;
        } catch (e) {}
    }

    elements.countIncBtn.addEventListener("click", async () => {
        try {
            const chan = (elements.obsChannelSelect && elements.obsChannelSelect.value) || state.selectedChannel || "";
            const res = await apiRequest("/api/counter", {
                method: "POST",
                body: JSON.stringify({ increment: 1, channel: chan })
            });
            state.counter = res.count;
            elements.counterNumber.textContent = state.counter;
            showToast(`Death count updated: ${state.counter}`, "success");
        } catch (e) {}
    });

    elements.countDecBtn.addEventListener("click", async () => {
        try {
            const chan = (elements.obsChannelSelect && elements.obsChannelSelect.value) || state.selectedChannel || "";
            const res = await apiRequest("/api/counter", {
                method: "POST",
                body: JSON.stringify({ increment: -1, channel: chan })
            });
            state.counter = res.count;
            elements.counterNumber.textContent = state.counter;
        } catch (e) {}
    });

    elements.countResetBtn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to reset the death counter to 0?")) return;
        try {
            const res = await apiRequest("/api/counter", {
                method: "POST",
                body: JSON.stringify({ count: 0 })
            });
            state.counter = res.count;
            elements.counterNumber.textContent = state.counter;
            showToast("Death counter reset to 0", "info");
        } catch (e) {}
    });

    elements.testBibleVerseBtn.addEventListener("click", async () => {
        try {
            showToast("Fetching Bible verse TTS...", "info");
            const chan = (elements.obsChannelSelect && elements.obsChannelSelect.value) || state.selectedChannel || "";
            const res = await apiRequest("/api/counter/test", {
                method: "POST",
                body: JSON.stringify({ channel: chan })
            });
            showToast("Bible verse TTS triggered!", "success");
        } catch (e) {}
    });

    // --- Chaos Mode UI Sync & Event Handlers ---
    function updateChaosUI(isChaos) {
        state.chaosMode = isChaos;
        if (elements.chaosToggleBtn) {
            if (isChaos) {
                elements.chaosToggleBtn.classList.add("active");
                if (elements.chaosBtnText) elements.chaosBtnText.textContent = "Chaos Mode: ON 🔥";
            } else {
                elements.chaosToggleBtn.classList.remove("active");
                if (elements.chaosBtnText) elements.chaosBtnText.textContent = "Chaos Mode: OFF";
            }
        }
        if (elements.prefChaosMode && elements.prefChaosMode.checked !== isChaos) {
            elements.prefChaosMode.checked = isChaos;
        }
    }

    async function toggleChaosMode(enable) {
        try {
            const body = (enable !== undefined) ? { enabled: enable } : {};
            if (state.selectedChannel) body.channel = state.selectedChannel;
            const res = await apiRequest("/api/chaos/toggle", {
                method: "POST",
                body: JSON.stringify(body)
            });
            updateChaosUI(res.chaos_mode);
            if (res.chaos_mode) {
                showToast("🔥 Chaos Mode Activated! All sounds play simultaneously!", "warning");
            } else {
                showToast("Chaos Mode Deactivated. Standard queue resumed.", "info");
            }
        } catch (e) {
            showToast("Failed to toggle Chaos Mode", "error");
        }
    }


    if (elements.chaosToggleBtn) {
        elements.chaosToggleBtn.addEventListener("click", () => {
            toggleChaosMode(!state.chaosMode);
        });
    }

    // --- Audio Queue Controls ---
    elements.skipAudioBtn.addEventListener("click", async () => {
        try {
            await apiRequest("/api/queue/skip", { method: "POST" });
            showToast("Audio skip request sent.", "info");
        } catch (e) {}
    });

    elements.clearQueueBtn.addEventListener("click", async () => {
        try {
            await apiRequest("/api/queue/clear", { method: "POST" });
            showToast("Audio queue cleared.", "info");
        } catch (e) {}
    });

    elements.clearChatLogBtn.addEventListener("click", () => {
        elements.chatLogList.innerHTML = '<div class="log-placeholder">Chat log cleared.</div>';
    });

    function appendChatLog(user, message) {
        if (elements.chatLogList.querySelector(".log-placeholder")) {
            elements.chatLogList.innerHTML = "";
        }
        const item = document.createElement("div");
        item.className = "chat-item";
        item.innerHTML = `<span class="user">@${escapeHtml(user)}:</span> ${escapeHtml(message)}`;
        elements.chatLogList.prepend(item);

        // Keep last 30 log items
        while (elements.chatLogList.children.length > 30) {
            elements.chatLogList.removeChild(elements.chatLogList.lastChild);
        }
    }

    // --- Server-Sent Events (SSE) Stream ---
    function initSseEvents() {
        const sse = new EventSource("/api/events");

        sse.addEventListener("status", (evt) => {
            try {
                const data = JSON.parse(evt.data);
                updateStatusUI(data);
                if (data.counter) {
                    state.counter = data.counter.count || 0;
                    elements.counterNumber.textContent = state.counter;
                }
            } catch (e) {}
        });

        sse.addEventListener("chaos_mode_update", (evt) => {
            try {
                const data = JSON.parse(evt.data);
                if (data.chaos_mode !== undefined) {
                    updateChaosUI(!!data.chaos_mode);
                }
            } catch (e) {}
        });

        sse.addEventListener("tts_chunk", (evt) => {
            try {
                const data = JSON.parse(evt.data);
                elements.currentSpeaker.textContent = data.user || "Chatter";
                elements.currentText.textContent = data.text || "...";
                elements.eqVisualizer.classList.add("active");
                appendChatLog(data.user || "Chatter", data.text || "");
            } catch (e) {}
        });

        sse.addEventListener("soundboard_trigger", (evt) => {
            try {
                const data = JSON.parse(evt.data);
                elements.currentSpeaker.textContent = `🔊 Soundboard (${data.sound_name})`;
                elements.currentText.textContent = `Triggered by @${data.user || "User"}`;
                appendChatLog(data.user || "Soundboard", `🔊 Triggered (${data.sound_name})`);
            } catch (e) {}
        });

        sse.addEventListener("chat_message", (evt) => {
            try {
                const data = JSON.parse(evt.data);
                appendChatLog(data.user, data.message);
            } catch (e) {}
        });

        sse.onerror = () => {
            elements.eqVisualizer.classList.remove("active");
        };
    }

    // --- Preferences Settings Handlers ---
    async function saveControlSettings() {
        if (!state.selectedChannel && state.channels.length > 0) {
            state.selectedChannel = state.channels[0];
        }
        if (!state.selectedChannel) {
            showToast("Please select a Twitch channel first.", "warning");
            return;
        }

        const body = {
            channel: state.selectedChannel,
            enable_8d_audio: elements.prefEnable8D ? elements.prefEnable8D.checked : true,
            effect_8d_speed: elements.pref8dSpeed ? parseFloat(elements.pref8dSpeed.value) : 0.5,
            enable_chat_responses: elements.prefChatResponses ? elements.prefChatResponses.checked : true,
            enable_kill_counter: elements.prefKillCounter ? elements.prefKillCounter.checked : true,
            enable_chaos_mode: elements.prefChaosMode ? elements.prefChaosMode.checked : false,
            same_user_timeout: elements.prefCooldown ? parseFloat(elements.prefCooldown.value) : 10
        };

        try {
            const res = await apiRequest("/api/control/settings", {
                method: "POST",
                body: JSON.stringify(body)
            });
            showToast(`Preferences updated for #${state.selectedChannel}!`, "success");
        } catch (e) {
            console.error("Failed to save settings", e);
        }
    }


    if (elements.prefEnable8D) {
        elements.prefEnable8D.addEventListener("change", () => {
            const speedGroup = document.getElementById("pref8dSpeedGroup");
            if (speedGroup) {
                speedGroup.style.opacity = elements.prefEnable8D.checked ? "1" : "0.5";
                speedGroup.style.pointerEvents = elements.prefEnable8D.checked ? "auto" : "none";
            }
            saveControlSettings();
        });
    }

    if (elements.pref8dSpeed) {
        elements.pref8dSpeed.addEventListener("input", () => {
            if (elements.pref8dSpeedVal) elements.pref8dSpeedVal.textContent = `${elements.pref8dSpeed.value}s`;
        });
        elements.pref8dSpeed.addEventListener("change", saveControlSettings);
    }

    if (elements.prefChatResponses) {
        elements.prefChatResponses.addEventListener("change", saveControlSettings);
    }

    if (elements.prefKillCounter) {
        elements.prefKillCounter.addEventListener("change", saveControlSettings);
    }

    if (elements.prefChaosMode) {
        elements.prefChaosMode.addEventListener("change", () => {
            toggleChaosMode(elements.prefChaosMode.checked);
        });
    }

    if (elements.prefCooldown) {
        elements.prefCooldown.addEventListener("input", () => {
            if (elements.prefCooldownVal) elements.prefCooldownVal.textContent = `${elements.prefCooldown.value}s`;
        });
        elements.prefCooldown.addEventListener("change", saveControlSettings);
    }

    // Initialize Auth & Status
    checkAuthStatus();
    loadInitialStatus();
    initSseEvents();
});
