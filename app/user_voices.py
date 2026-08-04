import json
import logging
import os
from typing import Dict, Any, Optional

from app.sanitizer import sanitize_identifier, sanitize_username

logger = logging.getLogger("UserVoices")

USER_VOICES_FILE = os.getenv("USER_VOICES_FILE", "user_voices.json")

class UserVoiceManager:
    """Manages persistent per-user voice mappings stored in a JSON file."""
    
    def __init__(self, filepath: str = USER_VOICES_FILE):
        self.filepath = filepath
        self._voices: Dict[str, Dict[str, Any]] = {}
        self.load()
        
    def load(self):
        """Load user voice mappings from JSON file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._voices = {}
                    for k, v in data.items():
                        user_clean = sanitize_username(k)
                        if not user_clean:
                            continue
                        if isinstance(v, dict):
                            voice_name = sanitize_identifier(v.get("voice"), max_len=100)
                            is_locked = bool(v.get("locked", False))
                        else:
                            voice_name = sanitize_identifier(v, max_len=100)
                            is_locked = False
                        
                        if voice_name:
                            self._voices[user_clean] = {"voice": voice_name, "locked": is_locked}
                logger.info(f"Loaded {len(self._voices)} user voice mappings from {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to load user voices from {self.filepath}: {e}")
                self._voices = {}
                
    def save(self):
        """Save user voice mappings to JSON file."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._voices, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self._voices)} user voice mappings to {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save user voices to {self.filepath}: {e}")
            
    def get_voice(self, username: Optional[str]) -> Optional[str]:
        """Get signature voice for username if registered."""
        if not username:
            return None
        user_clean = sanitize_username(username)
        entry = self._voices.get(user_clean)
        return entry.get("voice") if entry else None

    def is_locked(self, username: Optional[str]) -> bool:
        """Check if username signature voice is locked."""
        if not username:
            return False
        user_clean = sanitize_username(username)
        entry = self._voices.get(user_clean)
        return entry.get("locked", False) if entry else False
        
    def set_voice(self, username: str, voice_name: str, locked: bool = False, force: bool = False) -> str:
        """Set signature voice for username. Returns clean voice name."""
        user_clean = sanitize_username(username)
        if not user_clean:
            return "default"

        # Check existing lock if not forced (e.g. chat commands cannot override locks)
        if not force and self.is_locked(user_clean):
            entry = self._voices.get(user_clean)
            return entry.get("voice") if entry else "default"

        voice_clean = sanitize_identifier(voice_name, max_len=100).lower()
        
        if not voice_clean or voice_clean in ("reset", "clear", "default", "none"):
            if user_clean in self._voices:
                del self._voices[user_clean]
                self.save()
            return "default"
            
        self._voices[user_clean] = {"voice": voice_clean, "locked": locked}
        self.save()
        return voice_clean
        
    def clear_user(self, username: str, force: bool = False):
        """Remove signature voice for username."""
        user_clean = username.strip().lower()
        if not force and self.is_locked(user_clean):
            return
        if user_clean in self._voices:
            del self._voices[user_clean]
            self.save()
            
    def clear_all(self):
        """Clear all user voice mappings."""
        self._voices.clear()
        self.save()
        
    def get_all(self) -> Dict[str, Any]:
        """Return dict of all user voice mappings."""
        return dict(self._voices)

user_voice_manager = UserVoiceManager()
