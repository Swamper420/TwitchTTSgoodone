"""Audio loudness normalization (EBU R128 via ffmpeg loudnorm).

All TTS voices and soundboard files go through here so quiet whispers and
loud shout voices / sound effects play back at the same perceived loudness.

- Live path (per TTS chunk / per serve): single-pass loudnorm, fast (~100ms).
- Offline path (files on disk): two-pass loudnorm, most accurate.
- Graceful fallback: if ffmpeg is missing or fails, original bytes are returned.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

logger = logging.getLogger("AudioNorm")

_FFMPEG_OK: Optional[bool] = None


def is_ffmpeg_available() -> bool:
    """Cached check for ffmpeg binary."""
    global _FFMPEG_OK
    if _FFMPEG_OK is None:
        _FFMPEG_OK = shutil.which("ffmpeg") is not None
    return _FFMPEG_OK


def _norm_targets() -> Tuple[float, float, float]:
    """Read (I, TP, LRA) targets from config with safe defaults."""
    try:
        from app.config import config
        i = float(getattr(config, "audio_norm_target_i", -16.0))
        tp = float(getattr(config, "audio_norm_target_tp", -1.5))
        lra = float(getattr(config, "audio_norm_target_lra", 11.0))
    except (ValueError, TypeError):
        i, tp, lra = -16.0, -1.5, 11.0
    # Clamp to loudnorm valid ranges
    i = max(-70.0, min(-5.0, i))
    tp = max(-9.0, min(0.0, tp))
    lra = max(1.0, min(50.0, lra))
    return i, tp, lra


def _mime_for_format(fmt: str) -> str:
    fmt = (fmt or "wav").lower()
    if fmt == "mp3":
        return "audio/mpeg"
    if fmt == "ogg":
        return "audio/ogg"
    if fmt == "flac":
        return "audio/flac"
    if fmt in ("m4a", "mp4"):
        return "audio/mp4"
    return f"audio/{fmt}"


def _out_format(fmt: str) -> str:
    fmt = (fmt or "wav").lower()
    if fmt in ("mp3", "wav", "ogg", "flac"):
        return fmt
    if fmt in ("m4a", "mp4"):
        return "m4a"
    return "wav"


def is_normalization_enabled() -> bool:
    try:
        from app.config import config
        return bool(getattr(config, "enable_audio_norm", True))
    except Exception:
        return True


def normalize_audio_bytes(
    audio_bytes: bytes,
    audio_format: str = "wav",
) -> Tuple[bytes, str]:
    """Normalize loudness of in-memory audio (single-pass loudnorm).

    Returns (audio_bytes, mime_type). On any failure returns input unchanged.
    """
    fmt = _out_format(audio_format)
    mime = _mime_for_format(fmt)
    if not audio_bytes:
        return audio_bytes, mime
    if not is_normalization_enabled():
        return audio_bytes, mime
    if not is_ffmpeg_available():
        return audio_bytes, mime

    target_i, target_tp, target_lra = _norm_targets()
    in_tmp = None
    out_tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as f:
            f.write(audio_bytes)
            in_tmp = f.name
        out_tmp = in_tmp + f"_norm.{fmt}"
        filt = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", in_tmp,
            "-filter:a", filt,
            "-f", fmt,
            out_tmp,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if res.returncode == 0 and os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            with open(out_tmp, "rb") as f:
                return f.read(), mime
        logger.warning(
            "loudnorm single-pass warning (exit %s): %s",
            res.returncode, res.stderr.decode("utf-8", errors="ignore")[-500:],
        )
        return audio_bytes, mime
    except Exception as e:
        logger.warning(f"Audio normalization skipped: {e}")
        return audio_bytes, mime
    finally:
        for p in (in_tmp, out_tmp):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def _measure_loudness(file_path: str) -> Optional[Dict[str, float]]:
    """First pass: measure integrated loudness etc. Returns dict or None."""
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", file_path,
        "-filter:a", "loudnorm=print_format=json",
        "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             check=False, text=True)
        # ffmpeg prints JSON to stderr for loudnorm stats
        combined = (res.stderr or "") + "\n" + (res.stdout or "")
        start = combined.find("{")
        end = combined.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(combined[start:end + 1])
        return {
            "measured_I": float(data.get("input_i", data.get("measured_I", 0))),
            "measured_TP": float(data.get("input_tp", data.get("measured_TP", 0))),
            "measured_LRA": float(data.get("input_lra", data.get("measured_LRA", 0))),
            "measured_thresh": float(data.get("input_thresh", data.get("measured_thresh", -70))),
            "offset": float(data.get("target_offset", data.get("offset", 0))),
        }
    except Exception as e:
        logger.warning(f"loudnorm measure pass failed for '{file_path}': {e}")
        return None


def normalize_audio_file_inplace(file_path: str) -> bool:
    """Two-pass EBU R128 normalization of a file on disk, in place.

    Returns True if file was rewritten normalized, False otherwise.
    """
    if not os.path.isfile(file_path):
        return False
    if not is_ffmpeg_available():
        logger.warning("ffmpeg not available, skipping file normalization.")
        return False
    ext = os.path.splitext(file_path)[1].lower().lstrip(".") or "wav"
    fmt = _out_format(ext)
    target_i, target_tp, target_lra = _norm_targets()

    measured = _measure_loudness(file_path)
    if measured:
        filt = (
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
            f":measured_I={measured['measured_I']}"
            f":measured_TP={measured['measured_TP']}"
            f":measured_LRA={measured['measured_LRA']}"
            f":measured_thresh={measured['measured_thresh']}"
            f":offset={measured['offset']}:linear=true"
        )
    else:
        # Fall back to single-pass filter
        filt = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"

    out_tmp = file_path + f".norm.{fmt}"
    try:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", file_path,
            "-filter:a", filt,
            out_tmp,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if res.returncode == 0 and os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            os.replace(out_tmp, file_path)
            try:
                os.chmod(file_path, 0o644)
            except OSError:
                pass
            return True
        logger.warning(f"Could not normalize '{file_path}' (exit {res.returncode}).")
        if os.path.exists(out_tmp):
            try:
                os.remove(out_tmp)
            except Exception:
                pass
        return False
    except Exception as e:
        logger.warning(f"File normalization failed for '{file_path}': {e}")
        return False


def normalize_all_soundboard_files() -> Dict[str, int]:
    """Normalize every soundboard file on disk. Returns {'ok': n, 'failed': n, 'total': n}."""
    from app.soundboard import soundboard_manager
    sounds = soundboard_manager.get_available_sounds()
    ok = 0
    failed = 0
    for name, path in sounds.items():
        try:
            if normalize_audio_file_inplace(path):
                ok += 1
                logger.info(f"Normalized soundboard file '({name})' -> {path}")
            else:
                failed += 1
        except Exception as e:
            logger.warning(f"Failed to normalize '({name})': {e}")
            failed += 1
    return {"ok": ok, "failed": failed, "total": len(sounds)}
