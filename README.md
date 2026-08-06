# 🕹️ Steam 2004 Twitch TTS Bot with Local TTS API, Soundboard & OBS Overlay

A high-performance, modular Python Twitch Text-To-Speech (TTS) Bot featuring a local TTS API integration with caching, soundboard trigger system, kill/death counter with Bible verse TTS announcements, 8D audio processing, dual-server security architecture, and a classic Steam 2004 retro web overlay for OBS Studio.

---

## ✨ Key Features

- **Local TTS API Engine**: Synthesizes speech locally with in-memory hashing cache, auto-retry logic, and full parameter customization (`voice`, `model`, `language`, `speed`, `num_step`, `guidance_scale`, `seed`, and `format`).
- **Dual-Server Security Architecture**:
  - **Private Admin Server** (Default port `5000`): Full system control, credential configuration, bot management, and queue manipulation protected by `ADMIN_PASSWORD`.
  - **Public / OBS Overlay Server** (Default port `5001`): Dedicated public server hosting the read-only OBS overlay, internet-safe Streamer Control Portal, Standalone Audio Player, SSE event stream, and rate-limited public APIs.
- **Dedicated Read-Only OBS Studio Overlay**: Zero-delay WebAudio playback server with live spectrum visualizer, mute toggles, retro dark-green Steam 2004 aesthetic, and per-channel target routing (`?channel=channelname`).
- **OBS URL Query Modifiers**: Dynamically customize card positioning, volume, auto-hide on idle, font size, and chime sound directly via URL query parameters.
- **Built-in Soundboard & SFX System**: Scans local storage directories (`storage/soundboard`, `soundboard/`) supporting `.mp3`, `.wav`, `.ogg`, `.flac`, and `.m4a` files. Features fuzzy command matching (`!sounds`, `!sound <name>`, `!sfx`) and natural language queries.
- **Kill / Death Counter & Bible Verse TTS**: Monitors counter files (e.g. `values/deaths`) or HTTP API (`POST /api/counter`). Automatically fetches random Bible verses via multi-tier fallback APIs (`bible-api.com`, `labs.bible.org`, offline store) and reads configurable death text (e.g., `Kuolema {count}. {reference}: {text}`). Includes an **OBS Studio Lua script** (`darkcounter_obs.lua`).
- **Spatial 8D Audio & Shouting Voices**: Supports `{8d}` inline tags for 360-degree circular panning spatial audio via FFmpeg, configured shouting voice presets, and optional Chaos Mode for randomized audio parameters.
- **Smart Text Chunking & Normalization**: Automatically strips URLs, reduces spam, normalizes numbers/symbols, and splits text at natural clause boundaries (`.`, `!`, `?`, `,`, `;`) for low-latency audio generation.
- **Twitch Chat Bot & Signature Voices**: Dual-channel continuous IRC listener. Chatters can claim custom signature voices using `!myvoice <voicename>` or reset with `!myvoice reset`. Supports inline `[voicename]` multi-voice tags in single chat messages.
- **OWASP Security & Hardening**: Built-in rate limiters (login, TTS, counter, soundboard), XSS input sanitization, SSE client connection caps (`MAX_SSE_CLIENTS`, `MAX_SSE_PER_IP`), token validation, and password hashing.

---

## 🚀 Quick Start & Installation

### Prerequisites

- **Python**: 3.10 or newer
- **FFmpeg**: Required for audio mixing, 8D spatial effects, and audio format conversions (`sudo apt install ffmpeg` on Ubuntu/Debian)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Swamper420/TwitchTTSgoodone.git
cd TwitchTTSgoodone

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Running the Bot

```bash
# Launch server connecting to Twitch channel(s):
python3 main.py --channel "streamer1, streamer2" --port 5000 --public-port 5001
```

Once running, access the web interfaces:
- **Admin Dashboard** (Private): `http://localhost:5000`
- **Streamer Control Portal** (Public / Safe): `http://localhost:5001/control` (or `/user`)
- **Standalone Voice Player**: `http://localhost:5001/player`
- **Dedicated Read-Only OBS Overlay**: `http://localhost:5001/obs`

---

## 🌐 Web Interfaces & Port Routing

| Interface | URL Path | Access Level | Description |
| :--- | :--- | :--- | :--- |
| **Admin Dashboard** | `http://localhost:5000/` | Private (Port 5000) | Full management of bot settings, credentials, voice presets, and server state. Protected by `ADMIN_PASSWORD`. |
| **Control Portal** | `http://localhost:5001/control` | Public (Port 5001) | Internet-safe streamer portal for playback controls, soundboard triggers, and active voice list. |
| **Standalone Player** | `http://localhost:5001/player` | Public (Port 5001) | Browser audio player client for listening to TTS streams outside of OBS. |
| **OBS Studio Overlay** | `http://localhost:5001/obs` | Public (Port 5001) | Read-only browser source overlay designed for OBS Studio integration. |

---

## 📺 OBS Studio Setup & URL Query Modifiers

Add a **Browser Source** in OBS Studio pointing to `http://localhost:5001/obs`.

### Multi-Stream Channel Routing
- **All Joined Channels**: `http://localhost:5001/obs`
- **Channel 1 Only**: `http://localhost:5001/obs?channel=streamer1`
- **Channel 2 Only**: `http://localhost:5001/obs?channel=streamer2`

### Supported URL Query Modifiers

| Parameter | Example | Description |
| :--- | :--- | :--- |
| `?channel=name` or `?ch=name` | `?channel=shroud` | Target audio playback to a specific Twitch channel. |
| `?autohide=1` or `?hide_idle=1` | `?autohide=1` | Automatically hide the overlay UI card when speech is idle. |
| `?volume=0..100` | `?volume=80` | Override default audio playback volume level. |
| `?position=pos` or `?pos=pos` | `?pos=bottom-right` | Position overlay: `bottom-left`, `bottom-right`, `top-left`, `top-right`, or `center`. |
| `?chime=0` or `?chime=false` | `?chime=0` | Mute the chime notification sound preceding speech. |
| `?font_size=px` | `?font_size=24` | Custom font size for displayed chat text (in pixels). |

#### Combined URL Example:
```text
http://localhost:5001/obs?channel=streamer1&autohide=1&volume=75&position=bottom-right&font_size=22
```

---

## 🤖 Twitch Chat Commands & Multi-Voice Usage

The IRC bot supports exact and fuzzy command matching (powered by `RapidFuzz`) in English and Finnish.

### Command Reference

| Canonical Command | Supported Triggers / Aliases | Description |
| :--- | :--- | :--- |
| **`help`** | `!help`, `!tts`, `!botinfo`, `!info`, `!about`, `!ohje`, `!komennot` | Posts command guide and multi-voice instructions in Twitch chat. |
| **`voices`** | `!voices`, `!preset`, `!presets`, `!äänikö`, `!äänet` | Displays available voice presets. |
| **`myvoice`** | `!myvoice <voice>`, `!voice <name>`, `!omaääni <name>` | Sets user's signature voice. Use `random` for a random voice or `reset` to clear. |
| **`sounds`** | `!sounds`, `!soundboard`, `!sound <name>`, `!sfx`, `!efektit` | Lists or triggers soundboard audio effects. Accepts natural questions like *"what sounds"*. |
| **`skip`** | `!skip`, `!next`, `!ohita`, `!skippa`, `!seuraava` | Skips current TTS audio chunk and proceeds to next in queue. |
| **`clear`** | `!clear`, `!clearqueue`, `!stop`, `!tyhjennä` | Clears all pending TTS audio items in queue. |
| **`pieruta`** | `!pieruta`, `!fart`, `!pieru` | Plays a classic soundboard effect. |

### Multi-Voice Chat Tags
Users can switch voices mid-sentence by embedding `[voicename]` tags:
```text
Hello stream! [alice] Welcome everyone! [terry] Hope you enjoy the show!
```

---

## 🔊 Soundboard System

1. **Storage Location**: Place audio files (`.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`) in `storage/soundboard/` or `soundboard/`.
2. **Triggering**:
   - Via Chat: `!sound boom` or `!sfx airhorn`
   - Via Web UI: Click sound buttons in Streamer Control Portal (`/control`).
   - Via API: `POST /api/soundboard/trigger` with `{"sound": "boom"}`.

---

## 💀 Kill / Death Counter & DarkCounter OBS Lua Script

TwitchTTS includes a death counter system that triggers random Bible verse TTS announcements upon count increases.

### Features
- **File Watcher**: Monitors `values/deaths` (or custom configured file path).
- **REST API Endpoint**: `POST /api/counter` updates counter manually or via script.
- **Custom Template**: Default template `Kuolema {count}. {reference}: {text}`.
- **OBS Studio Integration**: Includes `darkcounter_obs.lua` script.

### OBS Studio Lua Script Setup
1. In OBS Studio, go to **Tools -> Scripts**.
2. Click **+** and select `darkcounter_obs.lua`.
3. Configure the **Server URL** (`http://localhost:5000`), **Counter File Path** (`values/deaths`), and optional **API Token**.

---

## 🎧 8D Spatial Audio & Audio Effects

- **Inline Tag**: Include `{8d}` in chat messages or TTS text to apply 360-degree spatial panning.
  ```text
  {8d} Listening to this in 8D spatial audio!
  ```
- **Configuration**: Adjust speed via `EFFECT_8D_SPEED` (default `0.5`) or toggle via `ENABLE_8D_AUDIO=true`.

---

## ⚙️ Configuration (`.env` File)

Copy `example.env` to `.env` to configure server defaults:

```env
# Local TTS API Endpoint & Defaults
TTS_API_URL=http://192.168.1.3:6969
TTS_VOICE=voice_fi
TTS_FORMAT=wav
TTS_LANGUAGE=fi
TTS_SPEED=1.0
TTS_NUM_STEP=32
TTS_GUIDANCE_SCALE=2.0
TTS_SEED=42

# Voice Presets & Shouting Voices
VOICE_PRESETS=voice_fi, mieto, terapisti, terry, tuomo4, niilo
SHOUTING_VOICES=mertaranta_fi

# Server Host & Ports
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
PUBLIC_SERVER_HOST=0.0.0.0
PUBLIC_SERVER_PORT=5001
SITE_DOMAIN=

# Authentication Passwords
ADMIN_PASSWORD=
CONTROL_PASSWORD=

# Twitch IRC Bot Credentials
TWITCH_CHANNEL=m_e_s_t_a_a_j_a
TWITCH_BOT_USERNAME=
TWITCH_OAUTH_TOKEN=
TWITCH_CLIENT_ID=
USER_TEMPLATE={user} sanoo: {text}
SAME_USER_TIMEOUT=10.0
ENABLE_CHAT_RESPONSES=true

# Soundboard & Audio Effects
ENABLE_SOUNDBOARD=true
SOUNDBOARD_DIR=storage/soundboard
EFFECT_8D_SPEED=0.5
ENABLE_8D_AUDIO=true

# Kill Counter & Bible API
ENABLE_KILL_COUNTER=true
KILL_COUNTER_FILE=values/deaths
KILL_COUNTER_POLL_INTERVAL=1.0
KILL_COUNTER_VOICE=terapisti
KILL_COUNTER_TEMPLATE=Kuolema {count}. {reference}: {text}
BIBLE_API_URL=https://bible-api.com/?random=verse
KILL_COUNTER_API_TOKEN=
```

---

## 💻 CLI Flags Reference

```bash
python3 main.py --help

  --channel CHANNEL, -c CHANNEL Twitch channel(s) to join (comma-separated, max 2)
  --port PORT, -p PORT          Admin web server port (default 5000)
  --public-port PUBLIC_PORT     Public server port for control portal, player & OBS overlay (default 5001)
  --obs-port OBS_PORT           Alias for --public-port
  --tts-url TTS_URL             Local TTS API endpoint URL
  --voice VOICE                 Default TTS voice preset override
  --model MODEL                 Default TTS model override
```

---

## 🧪 Running Unit Tests

Run the comprehensive unit test suite to verify system integrity:

```bash
./venv/bin/python3 -m unittest discover tests
```

---

## 📄 License & Credits

Built for Twitch streamers, content creators, and local TTS API enthusiasts. Retro Steam 2004 aesthetic inspired by classic gaming interfaces.
