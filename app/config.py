import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    tts_api_url: str = os.getenv("TTS_API_URL", "http://localhost:8080/api/tts")
    tts_model: Optional[str] = os.getenv("TTS_MODEL", None)
    tts_voice: Optional[str] = os.getenv("TTS_VOICE", None)
    tts_format: str = os.getenv("TTS_FORMAT", "wav")
    max_chunk_chars: int = int(os.getenv("MAX_CHUNK_CHARS", "100"))
    server_host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port: int = int(os.getenv("SERVER_PORT", "5000"))
    twitch_channel: str = os.getenv("TWITCH_CHANNEL", "")

config = Config()
