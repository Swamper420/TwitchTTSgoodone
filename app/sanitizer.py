import ipaddress
import os
import re
import urllib.parse
from typing import Any, Optional, Set, Tuple, List

ALLOWED_AUDIO_FORMATS: Set[str] = {"wav", "mp3", "ogg", "flac", "json"}



def escape_html(val: Any) -> str:
    """Safely convert value to string and HTML-escape characters to prevent XSS."""
    if val is None:
        return ""
    s = str(val)
    return (s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#039;"))


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


def sanitize_tts_url(val: Any, default: str = "http://localhost:8880") -> str:
    """Sanitize and validate TTS API URL against SSRF by restricting to local and private networks (OWASP API10:2023)."""
    s = sanitize_url(val, default="")
    if not s:
        return default
    parsed = urllib.parse.urlparse(s)
    hostname = parsed.hostname
    if not hostname:
        return default

    hostname = hostname.lower().strip("[]")
    if hostname in ("localhost", "localhost.localdomain", "::1") or hostname.endswith(".local"):
        return s.rstrip('/')

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return default
        if ip.is_private or ip.is_loopback:
            return s.rstrip('/')
    except ValueError:
        if hostname.startswith("192.168.") or hostname.startswith("10."):
            return s.rstrip('/')

    return default


ALLOWED_UPLOAD_EXTENSIONS: Set[str] = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
MAX_AUDIO_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5 MB limit


def verify_streamer_password(password_input: Any, active_channels: Optional[List[str]] = None) -> bool:
    """
    Verify if provided password matches any currently active Twitch channel/streamer name (case-insensitive).
    """
    if not password_input:
        return False
    clean_input = sanitize_username(password_input)
    if not clean_input:
        return False

    valid_channels = set()
    if active_channels:
        for ch in active_channels:
            c = sanitize_username(ch)
            if c:
                valid_channels.add(c)

    # Also check config channel settings if active_channels list was empty
    if not valid_channels:
        from app.config import config
        if getattr(config, "twitch_channel", ""):
            valid_channels.add(sanitize_username(config.twitch_channel))
        if getattr(config, "channels", None):
            for ch in config.channels:
                c = sanitize_username(ch)
                if c:
                    valid_channels.add(c)

    return clean_input in valid_channels


def validate_and_sanitize_audio_upload(
    file_bytes: bytes,
    filename: str,
    custom_sound_name: Optional[str] = None
) -> Tuple[str, str]:
    """
    Strictly sanitize and validate uploaded sound files.
    Enforces file size limit, extension whitelist, sound name sanitization,
    and binary magic header inspection to reject malicious or disguised files.
    Returns (clean_sound_name, clean_filename) on success, or raises ValueError.
    """
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    if len(file_bytes) > MAX_AUDIO_UPLOAD_SIZE:
        raise ValueError(f"File size ({len(file_bytes) / 1048576:.1f} MB) exceeds maximum allowed size of 5 MB.")

    # Determine extension from filename
    raw_name = sanitize_string(filename, max_len=255)
    if not raw_name:
        raise ValueError("Invalid filename.")

    ext = os.path.splitext(raw_name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(f"Unsupported file extension '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}")

    # Determine base sound identifier name
    base_candidate = custom_sound_name if custom_sound_name else os.path.splitext(raw_name)[0]
    clean_sound_name = sanitize_string(base_candidate, max_len=50).lower()
    clean_sound_name = re.sub(r'[^a-z0-9_\-]', '', clean_sound_name).strip('_-')

    if not clean_sound_name or len(clean_sound_name) < 2:
        raise ValueError("Sound name must be at least 2 characters (alphanumeric, hyphens, underscores).")

    clean_filename = f"{clean_sound_name}{ext}"

    # Strict Binary Magic Header Verification
    header = file_bytes[:16]

    if ext == ".mp3":
        # MP3 headers: ID3 tag or frame sync word (0xFF 0xFB/F3/F2/E3)
        has_id3 = file_bytes.startswith(b"ID3")
        has_sync = False
        if not has_id3:
            for i in range(min(len(file_bytes) - 1, 1024)):
                if file_bytes[i] == 0xFF and (file_bytes[i+1] & 0xE0) == 0xE0:
                    has_sync = True
                    break
        if not (has_id3 or has_sync):
            raise ValueError("File content does not match a valid MP3 audio header.")

    elif ext == ".wav":
        # WAV header: RIFF at offset 0, WAVE at offset 8
        if not (file_bytes.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WAVE"):
            raise ValueError("File content does not match a valid WAV audio header.")

    elif ext == ".ogg":
        # OGG header: OggS at offset 0
        if not file_bytes.startswith(b"OggS"):
            raise ValueError("File content does not match a valid OGG audio header.")

    elif ext == ".flac":
        # FLAC header: fLaC at offset 0
        if not file_bytes.startswith(b"fLaC"):
            raise ValueError("File content does not match a valid FLAC audio header.")

    elif ext == ".m4a":
        # M4A header: ftyp at offset 4
        if len(file_bytes) < 8 or file_bytes[4:8] != b"ftyp":
            raise ValueError("File content does not match a valid M4A container header.")

    return clean_sound_name, clean_filename

