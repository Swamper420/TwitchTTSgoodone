# 🎙️ Twitch TTS Bot with Local TTS API & Web Player

A lightweight, simple, and high-performance Python Twitch TTS (Text-To-Speech) Bot with a local TTS API client, text chunking, multi-voice tag support, and a sleek web audio overlay for streamers.

---

## ✨ Features

- **Local TTS API Integration**: Connects to `http://localhost:8080/api/tts` (GET or POST) supporting `text`, `voice`, `model`, and `format` (`wav`, `ogg`, `json`).
- **Multi-Voice Tag Support**: Users can trigger different voices within a single message using `[voicename]` tags (e.g. `[alice] Hello world! [bob] How are you?`).
- **Smart Text Chunking**: Automatically sanitizes messages (strips URLs, reduces spam) and splits text at sentence/clause boundaries (`.`, `!`, `?`, `,`, `;`) into smaller chunks for fast TTS generation and minimal audio latency.
- **Web Audio Player & Overlay**: Dark-mode dashboard and OBS Browser Source with live HTML5 Audio queue, visual equalizer, auto-play, skip track, volume controls, and live chat feed.
- **Anonymous Twitch Connection**: Connect to any public Twitch channel in read-only mode without needing Twitch API keys or OAuth setup!

---

## 🚀 Quick Start

### 1. Run the Bot & Web Interface

```bash
python3 main.py --channel streamername --port 5000
```

Open your browser to:
👉 **`http://localhost:5000`**

---

## 🎙️ Multi-Voice Tag Usage

Streamers and chatters can use `[voicename]` tags directly in Twitch chat or in the web test console:

```text
Hello everyone! [alice] Welcome to the stream! [bob] Glad to be here today!
```

- Text before any tag uses the default configured voice.
- Each `[voicename]` segment is split into chunks and generated using that voice name override.

---

## 📡 Local TTS API Endpoint Specs

The bot connects to your local TTS API at `http://localhost:8080/api/tts`.

### Parameters:
- `text` *(string, required)*: Text string to synthesize.
- `voice` *(string, optional)*: Reference voice filename or identifier.
- `model` *(string, optional)*: Model engine override.
- `format` *(string, optional)*: Output audio format — `"wav"`, `"ogg"`, `"pcm"`, or `"json"`.

### API Examples:
```bash
# 1. Download WAV speech file
curl -o speech.wav "http://localhost:8080/api/tts?text=Hello%20world&format=wav"

# 2. POST JSON payload
curl -X POST http://localhost:8080/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "alice", "format": "wav"}' \
  --output speech.wav
```

---

## 🖥️ OBS Studio Setup

1. Open **OBS Studio**.
2. Add a new **Browser Source**.
3. Set URL to `http://localhost:5000`.
4. Set Width: `800`, Height: `600`.
5. Check **Control audio via OBS** (optional) and click **OK**.

---

## ⚙️ Configuration & Options

Command-line flags:
```bash
python3 main.py --help
  --channel CHANNEL, -c CHANNEL Twitch channel name
  --port PORT, -p PORT          Web server port (default 5000)
  --tts-url TTS_URL             Local TTS API endpoint (default http://localhost:8080/api/tts)
  --voice VOICE                 Default voice override
  --model MODEL                 Default model override
  --max-chunk MAX_CHUNK         Max chunk length in characters (default 100)
```
