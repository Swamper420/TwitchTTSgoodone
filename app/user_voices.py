import json
import logging
import os
from typing import Dict, Optional

from app.sanitizer import sanitize_identifier, sanitize_username

logger = logging.getLogger("UserVoices")

USER_VOICES_FILE = os.getenv("USER_VOICES_FILE", "user_voices.json")

class UserVoiceManager:
    """Manages persistent per-user voice mappings stored in a JSON file."""
    
    def __init__(self, filepath: str = USER_VOICES_FILE):
        self.filepath = filepath
        self._voices: Dict[str, str] = {}
        self.load()
        
    def load(self):
        """Load user voice mappings from JSON file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._voices = {
                        sanitize_username(k): sanitize_identifier(v, max_len=100)
                        for k, v in data.items()
                        if k and v and sanitize_username(k) and sanitize_identifier(v, max_len=100)
                    }
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
        return self._voices.get(user_clean) if user_clean else None
        
    def set_voice(self, username: str, voice_name: str) -> str:
        """Set signature voice for username. Returns clean voice name."""
        user_clean = sanitize_username(username)
        if not user_clean:
            return "default"

        voice_clean = sanitize_identifier(voice_name, max_len=100).lower()
        
        if not voice_clean or voice_clean in ("reset", "clear", "default", "none"):
            if user_clean in self._voices:
                del self._voices[user_clean]
                self.save()
            return "default"
            
        self._voices[user_clean] = voice_clean
        self.save()
        return voice_clean
        
    def clear_user(self, username: str):
        """Remove signature voice for username."""
        user_clean = username.strip().lower()
        if user_clean in self._voices:
            del self._voices[user_clean]
            self.save()
            
    def clear_all(self):
        """Clear all user voice mappings."""
        self._voices.clear()
        self.save()
        
    def get_all(self) -> Dict[str, str]:
        """Return dict of all user voice mappings."""
        return dict(self._voices)

user_voice_manager = UserVoiceManager()
