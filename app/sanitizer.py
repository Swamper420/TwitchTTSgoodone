import re
import urllib.parse
from typing import Any, Optional, Set

ALLOWED_AUDIO_FORMATS: Set[str] = {"wav", "mp3", "ogg", "flac", "json"}


def sanitize_string(val: Any, max_len: int = 2000, default: str = "") -> str:
    """Safely convert value to string, strip control chars/null bytes, and enforce max length."""
    if val is None:
        return default
    if not isinstance(val, (str, int, float, bool)):
        return default
    s = str(val)
    # Remove null bytes and non-printable control characters except newline and tab
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s)
    s = s.strip()
    if max_len > 0 and len(s) > max_len:
        s = s[:max_len]
    return s


def sanitize_username(val: Any, max_len: int = 25) -> str:
    """Sanitize and validate Twitch/chat username (alphanumeric and underscores, no @ prefix)."""
    s = sanitize_string(val, max_len=max_len).lstrip("@").lstrip("#").lower()
    if not re.match(r'^[a-z0-9_]{1,25}$', s):
        return ""
    return s


def sanitize_channels_list(val: Any, max_channels: int = 2) -> str:
    """Sanitize input string containing 1 or 2 Twitch channel names separated by comma or space."""
    s = sanitize_string(val, max_len=100)
    if not s:
        return ""
    parts = re.split(r'[,;\s]+', s)
    valid_channels = []
    for p in parts:
        cleaned = sanitize_username(p)
        if cleaned and cleaned not in valid_channels:
            valid_channels.append(cleaned)
    return ", ".join(valid_channels[:max_channels])


def sanitize_speaker_name_for_tts(val: Any) -> str:
    r"""Strip symbols (.:_/\- etc) from speaker username so TTS pronounces it cleanly."""
    s = sanitize_string(val, max_len=100)
    if not s:
        return ""
    clean = re.sub(r'[^\w\s]|_', '', s).strip()
    return clean if clean else s



def sanitize_identifier(val: Any, max_len: int = 100, default: str = "") -> str:
    """Sanitize identifiers such as voice names, model names, chunk IDs (alphanumeric, -, _, .)."""
    s = sanitize_string(val, max_len=max_len, default=default)
    if not s:
        return default
    # Remove characters outside of alphanumeric, hyphen, underscore, and dot
    clean = re.sub(r'[^a-zA-Z0-9_\-.]', '', s)
    return clean if clean else default


def sanitize_int(val: Any, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    """Safely parse integer and clamp within optional min_val and max_val bounds."""
    try:
        if isinstance(val, bool):
            return default
        res = int(val)
    except (ValueError, TypeError):
        return default

    if min_val is not None and res < min_val:
        res = min_val
    if max_val is not None and res > max_val:
        res = max_val
    return res


def sanitize_float(val: Any, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    """Safely parse float and clamp within optional min_val and max_val bounds."""
    try:
        if isinstance(val, bool):
            return default
        res = float(val)
    except (ValueError, TypeError):
        return default

    if min_val is not None and res < min_val:
        res = min_val
    if max_val is not None and res > max_val:
        res = max_val
    return res



def sanitize_bool(val: Any, default: bool = False) -> bool:
    """Safely parse boolean value."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(val, (int, float)):
        return bool(val)
    return default


def sanitize_audio_format(val: Any, default: str = "wav") -> str:
    """Validate audio format against allowed formats set."""
    fmt = sanitize_identifier(val, max_len=10).lower()
    if fmt in ALLOWED_AUDIO_FORMATS:
        return fmt
    return default


def sanitize_url(val: Any, default: str = "http://localhost:8880") -> str:
    """Sanitize and validate http/https API URL."""
    s = sanitize_string(val, max_len=500, default=default)
    if not s:
        return default
    parsed = urllib.parse.urlparse(s)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return default
    return s.rstrip('/')
