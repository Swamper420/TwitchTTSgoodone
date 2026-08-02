import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger("Config")

ENV_KEYS = {
    "tts_api_url": "TTS_API_URL",
    "tts_model": "TTS_MODEL",
    "tts_voice": "TTS_VOICE",
    "tts_format": "TTS_FORMAT",
    "max_chunk_chars": "MAX_CHUNK_CHARS",
    "min_chunk_chars": "MIN_CHUNK_CHARS",
    "server_host": "SERVER_HOST",
    "server_port": "SERVER_PORT",
    "obs_server_host": "OBS_SERVER_HOST",
    "obs_server_port": "OBS_SERVER_PORT",
    "twitch_channel": "TWITCH_CHANNEL",
    "user_template": "USER_TEMPLATE",
    "voice_presets": "VOICE_PRESETS",
    "twitch_bot_username": "TWITCH_BOT_USERNAME",
    "twitch_oauth_token": "TWITCH_OAUTH_TOKEN",
    "enable_chat_responses": "ENABLE_CHAT_RESPONSES",
    "enable_periodic_info": "ENABLE_PERIODIC_INFO",
    "periodic_info_interval": "PERIODIC_INFO_INTERVAL",
    "admin_password": "ADMIN_PASSWORD",
    "twitch_client_id": "TWITCH_CLIENT_ID",
    "same_user_timeout": "SAME_USER_TIMEOUT",
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_dotenv(filepaths=(".env", "example.env"), override=False):
    """Lightweight loader for .env / example.env files into os.environ."""
    loaded_any = False
    for relative_or_abs in filepaths:
        candidates = [
            relative_or_abs if os.path.isabs(relative_or_abs) else os.path.join(BASE_DIR, relative_or_abs),
            relative_or_abs
        ]
        for path in candidates:
            if os.path.exists(path) and os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip()
                                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                                    v = v[1:-1]
                                elif " #" in v:
                                    v = v.split(" #")[0].strip()

                                if k:
                                    if override or k not in os.environ:
                                        os.environ[k] = v
                    logger.info(f"Loaded environment variables from {path}")
                    loaded_any = True
                    break
                except Exception as e:
                    logger.warning(f"Could not load {path}: {e}")
        if loaded_any:
            break
    return loaded_any

load_dotenv()

CONFIG_FILE = os.getenv("CONFIG_FILE", os.path.join(BASE_DIR, "config.json"))

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
    obs_server_host: str = field(default_factory=lambda: os.getenv("OBS_SERVER_HOST", "0.0.0.0"))
    obs_server_port: int = field(default_factory=lambda: int(os.getenv("OBS_SERVER_PORT", "5001")))
    twitch_channel: str = field(default_factory=lambda: os.getenv("TWITCH_CHANNEL", "m_e_s_t_a_a_j_a"))
    user_template: str = field(default_factory=lambda: os.getenv("USER_TEMPLATE", "{user} sanoo: {text}"))
    voice_presets: str = field(default_factory=lambda: os.getenv("VOICE_PRESETS", "mieto, terapisti, terry, tuomo4, niilo"))
    twitch_bot_username: str = field(default_factory=lambda: os.getenv("TWITCH_BOT_USERNAME", ""))
    twitch_oauth_token: str = field(default_factory=lambda: os.getenv("TWITCH_OAUTH_TOKEN", ""))
    enable_chat_responses: bool = field(default_factory=lambda: os.getenv("ENABLE_CHAT_RESPONSES", "true").lower() in ("true", "1", "yes"))
    enable_periodic_info: bool = field(default_factory=lambda: os.getenv("ENABLE_PERIODIC_INFO", "false").lower() in ("true", "1", "yes"))
    periodic_info_interval: int = field(default_factory=lambda: int(os.getenv("PERIODIC_INFO_INTERVAL", "15")))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))
    twitch_client_id: str = field(default_factory=lambda: os.getenv("TWITCH_CLIENT_ID", ""))
    same_user_timeout: float = field(default_factory=lambda: float(os.getenv("SAME_USER_TIMEOUT", "10.0")))

    def load(self, filepath: str = CONFIG_FILE):
        """Load configuration from JSON file if present, respecting environment variable overrides."""
        load_dotenv(override=False)

        # Apply environment variables to fields
        for key, env_var in ENV_KEYS.items():
            if hasattr(self, key) and env_var in os.environ:
                val_str = os.environ[env_var]
                curr_val = getattr(self, key)
                if isinstance(curr_val, bool):
                    setattr(self, key, val_str.lower() in ("true", "1", "yes"))
                elif isinstance(curr_val, int):
                    try:
                        setattr(self, key, int(val_str))
                    except ValueError:
                        pass
                elif isinstance(curr_val, float):
                    try:
                        setattr(self, key, float(val_str))
                    except ValueError:
                        pass
                else:
                    setattr(self, key, val_str)

        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, val in data.items():
                    if hasattr(self, key):
                        env_var = ENV_KEYS.get(key)
                        # If environment variable is set in os.environ, preserve environment value
                        if env_var and env_var in os.environ:
                            continue

                        if val is not None:
                            curr_val = getattr(self, key)
                            if isinstance(curr_val, bool):
                                if isinstance(val, bool):
                                    setattr(self, key, val)
                                else:
                                    setattr(self, key, str(val).lower() in ("true", "1", "yes"))
                            elif isinstance(curr_val, int):
                                setattr(self, key, int(val))
                            elif isinstance(curr_val, float):
                                setattr(self, key, float(val))
                            else:
                                setattr(self, key, str(val))
                logger.info(f"Loaded configuration from {filepath}")
            except Exception as e:
                logger.error(f"Failed to load config from {filepath}: {e}")
        
        self._sync_auth_manager()

    def save(self, filepath: str = CONFIG_FILE):
        """Save configuration to JSON file."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Saved configuration to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save config to {filepath}: {e}")
            
        self._sync_auth_manager()

    def _sync_auth_manager(self):
        try:
            from app.auth import dashboard_auth_manager
            dashboard_auth_manager.update_admin_password(self.admin_password)
        except Exception:
            pass

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
            "obs_server_host": self.obs_server_host,
            "obs_server_port": self.obs_server_port,
            "twitch_channel": self.twitch_channel,
            "user_template": self.user_template,
            "voice_presets": self.voice_presets,
            "twitch_bot_username": self.twitch_bot_username,
            "twitch_oauth_token": self.twitch_oauth_token,
            "enable_chat_responses": self.enable_chat_responses,
            "enable_periodic_info": self.enable_periodic_info,
            "periodic_info_interval": self.periodic_info_interval,
            "admin_password": self.admin_password,
            "twitch_client_id": self.twitch_client_id,
            "same_user_timeout": self.same_user_timeout,
        }

    def to_masked_dict(self) -> Dict[str, Any]:
        """Returns config dict with sensitive tokens and passwords masked for public/SSE endpoints."""
        d = self.to_dict()
        from app.auth import mask_token
        d["twitch_oauth_token"] = mask_token(self.twitch_oauth_token)
        d["has_admin_password"] = bool(self.admin_password)
        d["admin_password"] = "••••••••" if self.admin_password else ""
        return d

config = Config()
config.load()



