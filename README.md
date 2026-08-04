# 🕹️ Steam 2004 Twitch TTS Bot with Local TTS API & Web Overlay

A lightweight, simple, and high-performance Python Twitch TTS (Text-To-Speech) Bot with a local TTS API client, text chunking, multi-voice tag support, dual continuous stream support, and a classic Steam 2004 style web audio overlay for streamers.

---

## ✨ Features

- **Dual Continuous Stream Support**: Connect to up to 2 Twitch channels simultaneously (e.g. `channel1, channel2`).
- **Dedicated Read-Only OBS Overlay Server**: Runs on a separate dedicated port (default `5001`) with read-only security maxxing.
- **Per-Channel OBS Audio & Event Routing**: OBS overlay instances can target a specific channel via `?channel=channelname`.
- **OBS URL Modifiers**: Customize position, volume, auto-hide, font size, and chime sound directly via URL query parameters.
- **Steam 2004 Classic Aesthetic**: Retro dark-green interface with live spectrum visualizer, mute controls, and keyboard shortcuts.
- **Local TTS API Integration**: Connects to `http://localhost:8080/api/tts` (GET or POST) supporting `text`, `voice`, `model`, and `format` (`wav`, `ogg`, `json`).
- **Multi-Voice Tag Support**: Users can trigger different voices within a single message using `[voicename]` tags (e.g. `[alice] Hello world! [bob] How are you?`).
- **Smart Text Chunking & Sanitization**: Automatically strips URLs, reduces spam, and splits text at clause boundaries (`.`, `!`, `?`, `,`, `;`) into smaller chunks for low audio latency.
- **Twitch Chat Bot & Signature Voices**: Chatters can set signature TTS voices with `!myvoice <voicename>` and reset with `!myvoice reset`.
- **Modern Twitch OAuth 2.0 & Anonymous Mode**: Auto-detects bot username from OAuth token or connects anonymously in read-only mode (`justinfan`).

---

## 🚀 Quick Start & Usage Instructions

### 1. Installation

```bash
git clone https://github.com/Swamper420/TwitchTTSgoodone.git
cd TwitchTTSgoodone

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Running the Bot

```bash
# Connect to 1 or 2 Twitch channels on startup:
python3 main.py --channel "streamer1, streamer2" --port 5000 --obs-port 5001
```

Once running:
- **Streamer Control Portal (Internet-Safe End-User UI)**: `http://localhost:5000/control` (or `/user`)
- **Admin Dashboard**: `http://localhost:5000`
- **End-User Standalone Player**: `http://localhost:5000/player`
- **Dedicated Read-Only OBS Overlay**: `http://localhost:5001/obs`

---

## 📺 OBS Studio Setup & URL Modifiers

Add a **Browser Source** in OBS Studio pointing to the OBS Overlay Server (`http://localhost:5001/obs`).

### Single Stream / Multi-Stream URL Routing:
- **All Channels Combined**: `http://localhost:5001/obs`
- **Channel 1 Only**: `http://localhost:5001/obs?channel=channel1`
- **Channel 2 Only**: `http://localhost:5001/obs?channel=channel2`

### Supported URL Query Parameter Modifiers:

| Modifier | Example | Description |
| :--- | :--- | :--- |
| `?channel=name` or `?ch=name` | `?channel=shroud` | Target a specific Twitch stream instance for isolated audio. |
| `?autohide=1` or `?hide_idle=1` | `?autohide=1` | Automatically fade out the overlay card when idle (no active speech). |
| `?volume=80` | `?volume=70` | Override audio playback volume level (0 to 100). |
| `?position=pos` or `?pos=pos` | `?pos=bottom-right` | Position overlay: `bottom-left`, `bottom-right`, `top-left`, `top-right`, or `center`. |
| `?chime=0` or `?chime=false` | `?chime=0` | Disable the start notification chime sound before TTS audio. |
| `?font_size=20` | `?font_size=24` | Custom font size for the message text (in pixels). |

#### Combined Example:
```text
http://localhost:5001/obs?channel=shroud&autohide=1&volume=75&position=bottom-right&font_size=22
```

---

## 🤖 Twitch Chat Bot Commands

When bot OAuth credentials are provided:
- **`!help` / `!tts` / `!botinfo`**: Posts helpful info about TTS commands and multi-voice tags.
- **`!voices`**: Lists available voice presets.
- **`!myvoice <voicename>`**: Sets chatter's signature TTS voice (e.g. `!myvoice mieto`).
- **`!myvoice reset`**: Resets chatter's signature voice to default.

---

## 🎙️ Multi-Voice Chat Usage

Chatters can use inline `[voicename]` tags in chat:
```text
Hello everyone! [alice] Welcome to the stream! [bob] Glad to be here!
```

---

## ⚙️ Configuration & Environment

Command-line flags:
```bash
python3 main.py --help
  --channel CHANNEL, -c CHANNEL Twitch channel(s) to join (comma-separated, max 2)
  --port PORT, -p PORT          Admin web server port (default 5000)
  --obs-port OBS_PORT           Dedicated OBS overlay server port (default 5001)
  --tts-url TTS_URL             Local TTS API endpoint (default http://localhost:8080/api/tts)
  --voice VOICE                 Default voice override
  --model MODEL                 Default model override
  --max-chunk MAX_CHUNK         Max chunk length in characters
```

> 💡 **Note on `.env` vs Web UI settings:**  
> If `TWITCH_CHANNEL` is defined in your `.env` file, it will take priority on server startup. To make settings entered in the Web UI persist across restarts, leave `TWITCH_CHANNEL` empty or commented out in `.env` (e.g., `# TWITCH_CHANNEL=`).

---

## 🧪 Running Tests

```bash
./venv/bin/python3 -m unittest discover tests
```
