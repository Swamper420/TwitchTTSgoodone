import logging
import os
import re
from typing import Dict, List, Optional, Tuple, Any

try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

from app.config import config

logger = logging.getLogger("Soundboard")

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
}


class SoundboardManager:
    """Manages soundboard directory scanning, fuzzy matching via rapidfuzz, and trigger parsing."""

    def __init__(self, soundboard_dir: Optional[str] = None):
        self._custom_dir = soundboard_dir

    @property
    def directory(self) -> str:
        return self._custom_dir or config.soundboard_dir or "/storage/soundboard"

    def ensure_directory(self) -> str:
        target_dir = self.directory
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create soundboard directory '{target_dir}': {e}")
        return target_dir

    def get_available_sounds(self) -> Dict[str, str]:
        """
        Scan soundboard directory and return map of normalized_sound_name -> file_path.
        Example: {'boom': '/storage/soundboard/boom.mp3'}
        """
        target_dir = self.ensure_directory()
        sounds: Dict[str, str] = {}

        if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
            return sounds

        try:
            for entry in os.listdir(target_dir):
                full_path = os.path.join(target_dir, entry)
                if os.path.isfile(full_path):
                    ext = os.path.splitext(entry)[1].lower()
                    if ext in SUPPORTED_AUDIO_EXTENSIONS:
                        base_name = os.path.splitext(entry)[0].strip().lower()
                        if base_name:
                            sounds[base_name] = full_path
        except Exception as e:
            logger.error(f"Error scanning soundboard directory '{target_dir}': {e}")

        return sounds

    def find_sound(self, trigger: str, score_cutoff: float = 75.0) -> Optional[Tuple[str, str]]:
        """
        Find matching sound for trigger string.
        Returns tuple (matched_sound_name, file_path) or None.
        Matches exact (case-insensitive) first, then fuzzy via rapidfuzz if available.
        """
        cleaned_trigger = trigger.strip().lower()
        if not cleaned_trigger:
            return None

        sounds = self.get_available_sounds()
        if not sounds:
            return None

        # 1. Exact match (case-insensitive)
        if cleaned_trigger in sounds:
            return (cleaned_trigger, sounds[cleaned_trigger])

        # 2. Fuzzy match via RapidFuzz
        if HAS_RAPIDFUZZ and len(sounds) > 0:
            candidates = list(sounds.keys())
            match = process.extractOne(
                cleaned_trigger,
                candidates,
                scorer=fuzz.WRatio,
                score_cutoff=score_cutoff
            )
            if match:
                best_name, score, _ = match
                logger.info(f"Fuzzy matched soundboard trigger '({trigger})' -> '{best_name}' (score: {score:.1f})")
                return (best_name, sounds[best_name])

        return None

    def parse_soundboard_text(self, text: str, score_cutoff: float = 75.0) -> List[Dict[str, Any]]:
        """
        Parse raw text containing (sound_name) triggers into a sequence of segments.
        Example: "Hello (boom) world (bruh)"
        -> [
             {"type": "text", "content": "Hello "},
             {"type": "soundboard", "sound_name": "boom", "file_path": "/storage/soundboard/boom.mp3", "raw_trigger": "(boom)"},
             {"type": "text", "content": " world "},
             {"type": "soundboard", "sound_name": "bruh", "file_path": "/storage/soundboard/bruh.mp3", "raw_trigger": "(bruh)"}
           ]
        """
        if not text or not config.enable_soundboard:
            return [{"type": "text", "content": text}] if text else []

        pattern = r'\(([^()\n]+)\)'
        segments: List[Dict[str, Any]] = []

        last_idx = 0
        for match in re.finditer(pattern, text):
            start, end = match.span()
            trigger_content = match.group(1).strip()

            # Text before trigger
            if start > last_idx:
                prev_text = text[last_idx:start]
                if prev_text:
                    segments.append({"type": "text", "content": prev_text})

            sound_match = self.find_sound(trigger_content, score_cutoff=score_cutoff)
            if sound_match:
                sound_name, file_path = sound_match
                segments.append({
                    "type": "soundboard",
                    "sound_name": sound_name,
                    "file_path": file_path,
                    "raw_trigger": match.group(0)
                })
            else:
                # Not a valid soundboard trigger, treat as regular text
                segments.append({"type": "text", "content": match.group(0)})

            last_idx = end

        # Remaining text after last match
        if last_idx < len(text):
            rem_text = text[last_idx:]
            if rem_text:
                segments.append({"type": "text", "content": rem_text})

        return segments

    def get_mime_type(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        return MIME_TYPES.get(ext, "audio/mpeg")


soundboard_manager = SoundboardManager()
