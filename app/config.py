import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger("Config")

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")

@dataclass
class Config:
    tts_api_url: str = field(default_factory=lambda: os.getenv("TTS_API_URL", "http://192.168.1.3:6969/api/tts"))
    tts_model: Optional[str] = field(default_factory=lambda: os.getenv("TTS_MODEL", ""))
    tts_voice: Optional[str] = field(default_factory=lambda: os.getenv("TTS_VOICE", "mieto"))
    tts_format: str = field(default_factory=lambda: os.getenv("TTS_FORMAT", "ogg"))
    max_chunk_chars: int = field(default_factory=lambda: int(os.getenv("MAX_CHUNK_CHARS", "50")))
    min_chunk_chars: int = field(default_factory=lambda: int(os.getenv("MIN_CHUNK_CHARS", "10")))
    server_host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    server_port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "5000")))
    twitch_channel: str = field(default_factory=lambda: os.getenv("TWITCH_CHANNEL", "m_e_s_t_a_a_j_a"))
    user_template: str = field(default_factory=lambda: os.getenv("USER_TEMPLATE", "{user} sanoo: {text}"))
    voice_presets: str = field(default_factory=lambda: os.getenv("VOICE_PRESETS", "mieto, terapisti, terry, tuomo4, niilo"))
    twitch_bot_username: str = field(default_factory=lambda: os.getenv("TWITCH_BOT_USERNAME", ""))
    twitch_oauth_token: str = field(default_factory=lambda: os.getenv("TWITCH_OAUTH_TOKEN", ""))
    enable_chat_responses: bool = field(default_factory=lambda: os.getenv("ENABLE_CHAT_RESPONSES", "true").lower() in ("true", "1", "yes"))
    enable_periodic_info: bool = field(default_factory=lambda: os.getenv("ENABLE_PERIODIC_INFO", "false").lower() in ("true", "1", "yes"))
    periodic_info_interval: int = field(default_factory=lambda: int(os.getenv("PERIODIC_INFO_INTERVAL", "15")))

    def load(self, filepath: str = CONFIG_FILE):
        """Load configuration from JSON file if present."""
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, val in data.items():
                    if hasattr(self, key) and val is not None:
                        curr_val = getattr(self, key)
                        if isinstance(curr_val, bool):
                            if isinstance(val, bool):
                                setattr(self, key, val)
                            else:
                                setattr(self, key, str(val).lower() in ("true", "1", "yes"))
                        elif isinstance(curr_val, int):
                            setattr(self, key, int(val))
                        else:
                            setattr(self, key, str(val) if val is not None else "")
                logger.info(f"Loaded configuration from {filepath}")
            except Exception as e:
                logger.error(f"Failed to load config from {filepath}: {e}")

    def save(self, filepath: str = CONFIG_FILE):
        """Save configuration to JSON file."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Saved configuration to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save config to {filepath}: {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tts_api_url": self.tts_api_url,
            "tts_model": self.tts_model or "",
            "tts_voice": self.tts_voice or "",
            "tts_format": self.tts_format,
            "max_chunk_chars": self.max_chunk_chars,
            "min_chunk_chars": self.min_chunk_chars,
            "server_host": self.server_host,
            "server_port": self.server_port,
            "twitch_channel": self.twitch_channel,
            "user_template": self.user_template,
            "voice_presets": self.voice_presets,
            "twitch_bot_username": self.twitch_bot_username,
            "twitch_oauth_token": self.twitch_oauth_token,
            "enable_chat_responses": self.enable_chat_responses,
            "enable_periodic_info": self.enable_periodic_info,
            "periodic_info_interval": self.periodic_info_interval,
        }

config = Config()
config.load()

