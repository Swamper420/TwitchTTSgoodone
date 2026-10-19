"""Per-user distinct voice effects (pitch key + vertical placement).

When FORCE_DISTINCT_USER_VOICES is enabled, every chatter gets a stable,
username-derived voice color on top of whatever base TTS voice is used
(inline [voice] tag, !myvoice signature, or global default). Two chatters
using the exact same base voice still sound clearly different.

- Pitch key: dramatic semitone shift in [-span, +span] via ffmpeg
  (asetrate resampling = chipmunk/deep "different key" effect, tempo
  compensated with atempo so speech rate stays natural).
- Vertical placement ("above" vs "under the streamer"): psychoacoustic EQ
  + echo recipe. Above = bright treble lift with a short early reflection.
  Under = muffled lowpass with chesty bass boost.

Mapping is deterministic per username (sha256), so a user always sounds
the same across messages, and neighbours on the hash ring sound far apart.
"""

import hashlib
import logging
import math
import os
import subprocess
import tempfile
from typing import Optional, Tuple

logger = logging.getLogger("VoiceEffects")


def _hash_int(username: str) -> int:
    clean = (username or "").strip().lower()
    digest = hashlib.sha256(clean.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def user_semitone_offset(username: str, span: float = 7.0) -> float:
    """Stable per-user pitch offset in semitones within [-span, +span].

    Quantized to 0.5 semitone steps. A deadzone around 0 is pushed out to
    at least +/-1.5 semitones so the difference is always clearly audible
    ("quite dramatic" by default with span=7).
    """
    try:
        span_val = float(span)
    except (TypeError, ValueError):
        span_val = 7.0
    span_val = max(1.0, min(12.0, span_val))

    # 0.5-semitone buckets across the full range
    steps = int(span_val * 2) * 2 + 1  # e.g. span 7 -> 29 buckets
    bucket = _hash_int(f"pitch:{username}") % steps
    semitones = (bucket - (steps // 2)) * 0.5

    if abs(semitones) < 1.5:
        semitones = 1.5 if (_hash_int(f"sign:{username}") % 2 == 0) else -1.5
        semitones = max(-span_val, min(span_val, semitones))
    return float(semitones)


def user_vertical_mode(username: str) -> str:
    """Stable per-user vertical placement: 'above' or 'below'."""
    return "above" if (_hash_int(f"vertical:{username}") % 2 == 0) else "below"


def describe_user_voice(username: str, span: float = 7.0) -> dict:
    """Human-readable description of a user's distinct voice color."""
    offset = user_semitone_offset(username, span)
    vertical = user_vertical_mode(username)
    return {
        "username": username,
        "semitones": offset,
        "vertical": vertical,
        "label": f"{offset:+.1f}st/{vertical}",
    }


def _split_atempo(factor: float) -> list:
    """Split a tempo factor into atempo-compatible (0.5..2.0) stages."""
    if 0.5 <= factor <= 2.0:
        return [f"atempo={factor:.4f}"]
    # Two equal stages always land in range for our pitch spans.
    half = math.sqrt(factor)
    half = max(0.5, min(2.0, half))
    return [f"atempo={half:.4f}", f"atempo={factor / half:.4f}"]


def apply_distinct_user_voice(
    audio_bytes: bytes,
    audio_format: str = "wav",
    username: str = "",
    span: float = 7.0,
    vertical: bool = True,
) -> Tuple[bytes, str]:
    """Apply per-user pitch + vertical EQ to TTS audio bytes.

    Returns (audio_bytes, mime_type); falls back to input on any error
    (missing ffmpeg, empty input, ...).
    """
    if not audio_bytes:
        fmt = audio_format or "wav"
        mime = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
        return audio_bytes, mime

    fmt = audio_format or "wav"
    out_fmt = "wav" if fmt not in ("mp3", "wav", "ogg") else fmt
    mime_type = "audio/mpeg" if out_fmt == "mp3" else f"audio/{out_fmt}"

    if not username:
        return audio_bytes, mime_type

    semitones = user_semitone_offset(username, span)
    placement = user_vertical_mode(username) if vertical else "flat"
    pitch_factor = 2.0 ** (semitones / 12.0)

    filters = ["aresample=44100"]
    if abs(semitones) >= 0.25:
        filters.append(f"asetrate=44100*{pitch_factor:.4f}")
        filters.append("aresample=44100")
        filters.extend(_split_atempo(1.0 / pitch_factor))
    if placement == "above":
        # Bright + a breath of early reflection: sounds "above".
        filters.append("treble=g=8:f=3500:w=0.8")
        filters.append("aecho=0.5:0.6:12:0.12")
    elif placement == "below":
        # Muffled + chesty: sounds like it's coming from "under".
        filters.append("lowpass=f=3200")
        filters.append("bass=g=8:f=180:w=0.9")
    filter_str = ",".join(filters)

    in_tmp: Optional[str] = None
    out_tmp: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{out_fmt}", delete=False) as f:
            f.write(audio_bytes)
            in_tmp = f.name
        out_tmp = in_tmp + f"_distinct.{out_fmt}"
        cmd = [
            "ffmpeg", "-y",
            "-i", in_tmp,
            "-filter_complex", f"[0:a]{filter_str}[aout]",
            "-map", "[aout]",
            "-f", out_fmt,
            out_tmp,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if res.returncode == 0 and os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            with open(out_tmp, "rb") as f:
                processed = f.read()
            logger.info(
                f"🎭 Distinct user voice for '{username}': "
                f"{semitones:+.1f}st/{placement} ({len(processed)} bytes)."
            )
            return processed, mime_type
        logger.warning(
            f"distinct voice ffmpeg warning (exit {res.returncode}): "
            f"{res.stderr.decode('utf-8', errors='ignore')[-300:]}"
        )
        return audio_bytes, mime_type
    except FileNotFoundError:
        logger.warning("distinct voice skipped: ffmpeg not found")
        return audio_bytes, mime_type
    except Exception as e:
        logger.warning(f"distinct voice skipped: {e}")
        return audio_bytes, mime_type
    finally:
        for tmp in (in_tmp, out_tmp):
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
