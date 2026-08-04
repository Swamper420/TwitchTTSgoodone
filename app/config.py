import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

logger = logging.getLogger("Config")

ENV_KEYS = {
    "tts_api_url": "TTS_API_URL",
    "tts_model": "TTS_MODEL",
    "tts_voice": "TTS_VOICE",
    "tts_format": "TTS_FORMAT",
    "tts_language": "TTS_LANGUAGE",
    "tts_speed": "TTS_SPEED",
    "tts_num_step": "TTS_NUM_STEP",
    "tts_guidance_scale": "TTS_GUIDANCE_SCALE",
    "tts_seed": "TTS_SEED",
    "server_host": "SERVER_HOST",
    "server_port": "SERVER_PORT",
    "public_server_host": "PUBLIC_SERVER_HOST",
    "public_server_port": "PUBLIC_SERVER_PORT",
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
    "enable_kill_counter": "ENABLE_KILL_COUNTER",
    "kill_counter_file": "KILL_COUNTER_FILE",
    "kill_counter_poll_interval": "KILL_COUNTER_POLL_INTERVAL",
    "kill_counter_voice": "KILL_COUNTER_VOICE",
    "kill_counter_template": "KILL_COUNTER_TEMPLATE",
    "bible_api_url": "BIBLE_API_URL",
    "kill_counter_api_token": "KILL_COUNTER_API_TOKEN",
    "soundboard_dir": "SOUNDBOARD_DIR",
    "enable_soundboard": "ENABLE_SOUNDBOARD",
    "shouting_voices": "SHOUTING_VOICES",
    "shoutingvoices": "SHOUTING_VOICES",
    "effect_8d_speed": "EFFECT_8D_SPEED",
    "eight_d_speed": "EFFECT_8D_SPEED",
    "8d_speed": "EFFECT_8D_SPEED",
    "enable_8d_audio": "ENABLE_8D_AUDIO",
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
    tts_api_url: str = field(default_factory=lambda: os.getenv("TTS_API_URL", "http://192.168.1.3:6969"))
    tts_model: Optional[str] = field(default_factory=lambda: os.getenv("TTS_MODEL", ""))
    tts_voice: Optional[str] = field(default_factory=lambda: os.getenv("TTS_VOICE", "voice_fi"))
    tts_format: str = field(default_factory=lambda: os.getenv("TTS_FORMAT", "wav"))
    tts_language: str = field(default_factory=lambda: os.getenv("TTS_LANGUAGE", "fi"))
    tts_speed: float = field(default_factory=lambda: float(os.getenv("TTS_SPEED", "1.0")))
    tts_num_step: int = field(default_factory=lambda: int(os.getenv("TTS_NUM_STEP", "32")))
    tts_guidance_scale: float = field(default_factory=lambda: float(os.getenv("TTS_GUIDANCE_SCALE", "2.0")))
    tts_seed: int = field(default_factory=lambda: int(os.getenv("TTS_SEED", "42")))
    server_host: str = field(default_factory=lambda: os.getenv("SERVER_HOST", "0.0.0.0"))
    server_port: int = field(default_factory=lambda: int(os.getenv("SERVER_PORT", "5000")))
    # Public server (internet-facing): serves control portal, player, and OBS overlay
    # Falls back to legacy OBS_SERVER_HOST/PORT env vars for backward compatibility
    public_server_host: str = field(default_factory=lambda: os.getenv("PUBLIC_SERVER_HOST", os.getenv("OBS_SERVER_HOST", "0.0.0.0")))
    public_server_port: int = field(default_factory=lambda: int(os.getenv("PUBLIC_SERVER_PORT", os.getenv("OBS_SERVER_PORT", "5001"))))
    # Legacy aliases (kept for backward compat with config.json)
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
    user_password: str = field(default_factory=lambda: os.getenv("USER_PASSWORD", os.getenv("CONTROL_PASSWORD", "")))
    twitch_client_id: str = field(default_factory=lambda: os.getenv("TWITCH_CLIENT_ID", ""))
    same_user_timeout: float = field(default_factory=lambda: float(os.getenv("SAME_USER_TIMEOUT", "10.0")))
    enable_kill_counter: bool = field(default_factory=lambda: os.getenv("ENABLE_KILL_COUNTER", "true").lower() in ("true", "1", "yes"))
    kill_counter_file: str = field(default_factory=lambda: os.getenv("KILL_COUNTER_FILE", "values/deaths"))
    kill_counter_poll_interval: float = field(default_factory=lambda: float(os.getenv("KILL_COUNTER_POLL_INTERVAL", "1.0")))
    kill_counter_voice: str = field(default_factory=lambda: os.getenv("KILL_COUNTER_VOICE", "terapisti"))
    kill_counter_template: str = field(default_factory=lambda: os.getenv("KILL_COUNTER_TEMPLATE", "Kuolema {count}. {reference}: {text}"))
    bible_api_url: str = field(default_factory=lambda: os.getenv("BIBLE_API_URL", "https://bible-api.com/?random=verse"))
    kill_counter_api_token: str = field(default_factory=lambda: os.getenv("KILL_COUNTER_API_TOKEN", ""))
    soundboard_dir: str = field(default_factory=lambda: os.getenv("SOUNDBOARD_DIR", os.path.join(BASE_DIR, "storage", "soundboard")))
    enable_soundboard: bool = field(default_factory=lambda: os.getenv("ENABLE_SOUNDBOARD", "true").lower() in ("true", "1", "yes"))
    shouting_voices: str = field(default_factory=lambda: os.getenv("SHOUTING_VOICES", "mertaranta_fi"))
    effect_8d_speed: float = field(default_factory=lambda: float(os.getenv("EFFECT_8D_SPEED", "0.5")))
    enable_8d_audio: bool = field(default_factory=lambda: os.getenv("ENABLE_8D_AUDIO", "true").lower() in ("true", "1", "yes"))

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
                    target_key = "shouting_voices" if key in ("shouting_voices", "shoutingvoices") else key
                    if hasattr(self, target_key):
                        env_var = ENV_KEYS.get(key)
                        # If environment variable is set in os.environ, preserve environment value
                        if env_var and env_var in os.environ:
                            continue

                        if val is not None:
                            curr_val = getattr(self, target_key)
                            if isinstance(curr_val, bool):
                                if isinstance(val, bool):
                                    setattr(self, target_key, val)
                                else:
                                    setattr(self, target_key, str(val).lower() in ("true", "1", "yes"))
                            elif isinstance(curr_val, int):
                                setattr(self, target_key, int(val))
                            elif isinstance(curr_val, float):
                                setattr(self, target_key, float(val))
                            else:
                                setattr(self, target_key, str(val))
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
            dashboard_auth_manager.update_passwords(self.admin_password, self.user_password)
        except Exception:
            pass

    @property
    def shouting_voices_list(self) -> List[str]:
        """Returns list of preset shouting voice names from shouting_voices config."""
        if not self.shouting_voices:
            return ["mertaranta_fi"]
        if isinstance(self.shouting_voices, list):
            voices = [str(v).strip() for v in self.shouting_voices if str(v).strip()]
        else:
            voices = [v.strip() for v in str(self.shouting_voices).replace(";", ",").split(",") if v.strip()]
        return voices if voices else ["mertaranta_fi"]

    @property
    def channels(self) -> List[str]:
        """Returns up to 2 cleaned Twitch channel names from twitch_channel."""
        if not self.twitch_channel:
            return []
        raw_list = [c.strip().lstrip("#").lower() for c in self.twitch_channel.replace(";", ",").split(",") if c.strip()]
        unique_channels = []
        for ch in raw_list:
            if ch and ch not in unique_channels:
                unique_channels.append(ch)
        return unique_channels[:2]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tts_api_url": self.tts_api_url,
            "tts_model": self.tts_model or "",
            "tts_voice": self.tts_voice or "",
            "tts_format": self.tts_format,
            "tts_language": self.tts_language,
            "tts_speed": self.tts_speed,
            "tts_num_step": self.tts_num_step,
            "tts_guidance_scale": self.tts_guidance_scale,
            "tts_seed": self.tts_seed,
            "server_host": self.server_host,
            "server_port": self.server_port,
            "public_server_host": self.public_server_host,
            "public_server_port": self.public_server_port,
            "obs_server_host": self.public_server_host,
            "obs_server_port": self.public_server_port,
            "twitch_channel": self.twitch_channel,
            "channels": self.channels,
            "user_template": self.user_template,
            "voice_presets": self.voice_presets,
            "twitch_bot_username": self.twitch_bot_username,
            "twitch_oauth_token": self.twitch_oauth_token,
            "enable_chat_responses": self.enable_chat_responses,
            "enable_periodic_info": self.enable_periodic_info,
            "periodic_info_interval": self.periodic_info_interval,
            "admin_password": self.admin_password,
            "user_password": self.user_password,
            "twitch_client_id": self.twitch_client_id,
            "same_user_timeout": self.same_user_timeout,
            "kill_counter_api_token": self.kill_counter_api_token,
            "soundboard_dir": self.soundboard_dir,
            "enable_soundboard": self.enable_soundboard,
            "shouting_voices": self.shouting_voices,
            "effect_8d_speed": self.effect_8d_speed,
            "enable_8d_audio": self.enable_8d_audio,
            "enable_kill_counter": self.enable_kill_counter,
            "kill_counter_file": self.kill_counter_file,
            "kill_counter_poll_interval": self.kill_counter_poll_interval,
            "kill_counter_voice": self.kill_counter_voice,
            "kill_counter_template": self.kill_counter_template,
            "bible_api_url": self.bible_api_url,
        }

    def to_masked_dict(self) -> Dict[str, Any]:
        """Returns config dict with sensitive tokens and passwords masked for public/SSE endpoints."""
        d = self.to_dict()
        from app.auth import mask_token
        d["twitch_oauth_token"] = mask_token(self.twitch_oauth_token)
        d["kill_counter_api_token"] = mask_token(self.kill_counter_api_token)
        d["has_admin_password"] = bool(self.admin_password)
        d["admin_password"] = "••••••••" if self.admin_password else ""
        d["has_user_password"] = bool(self.user_password)
        d["user_password"] = "••••••••" if self.user_password else ""
        return d

config = Config()
config.load()



