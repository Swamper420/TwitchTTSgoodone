import base64
import hashlib
import logging
import time
from typing import Dict, Any, Optional, Tuple
import requests

from app.config import config
from app.sanitizer import sanitize_identifier, sanitize_audio_format

logger = logging.getLogger("TTSClient")

class TTSClient:
    """Client for local TTS API with in-memory caching and automatic retries."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or config.tts_api_url).rstrip('/')
        self._cache: Dict[str, Tuple[bytes, str]] = {}
        self._max_cache_entries = 250

    def _compute_cache_key(
        self,
        text: str,
        voice: str,
        language: str,
        speed: float,
        num_step: int,
        guidance_scale: float,
        fmt: str,
        seed: int
    ) -> str:
        key_str = f"{text}|{voice}|{language}|{speed}|{num_step}|{guidance_scale}|{fmt}|{seed}"
        return hashlib.sha256(key_str.encode('utf-8')).hexdigest()

    def get_voices(self, timeout: float = 10.0) -> Dict[str, Any]:
        """Fetch list of voices from GET /api/v1/voices."""
        url = self.base_url if self.base_url.endswith("/api/v1/voices") else f"{self.base_url}/api/v1/voices"
        res = requests.get(url, timeout=timeout)
        res.raise_for_status()
        return res.json()

    def reload_voices(self, timeout: float = 10.0) -> Dict[str, Any]:
        """Trigger voice catalog rescan via POST /api/v1/voices/reload."""
        url = self.base_url if self.base_url.endswith("/api/v1/voices/reload") else f"{self.base_url}/api/v1/voices/reload"
        res = requests.post(url, timeout=timeout)
        res.raise_for_status()
        return res.json()

    def health_check(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Check API health via GET /health."""
        # For health check, route to /health relative to server base host if needed
        base = self.base_url.rsplit('/api', 1)[0] if '/api' in self.base_url else self.base_url
        url = f"{base}/health"
        res = requests.get(url, timeout=timeout)
        res.raise_for_status()
        return res.json()

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        language: Optional[str] = None,
        speed: Optional[float] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        audio_format: Optional[str] = None,
        response_format: Optional[str] = None,
        seed: Optional[int] = None,
        method: str = "POST",
        timeout: float = 45.0,
        max_retries: int = 3,
        **kwargs
    ) -> Tuple[bytes, str]:
        """
        Synthesize text to audio using new TTS API (POST /api/v1/tts).
        Returns tuple of (audio_bytes, mime_type).
        """
        raw_voice = voice or config.tts_voice or "voice_fi"
        raw_format = response_format or audio_format or config.tts_format or "wav"
        
        voice_to_use = sanitize_identifier(raw_voice, max_len=100) if raw_voice else "voice_fi"
        format_to_use = sanitize_audio_format(raw_format, default="wav")
        language_to_use = language or getattr(config, "tts_language", "fi") or "fi"
        speed_to_use = float(speed if speed is not None else getattr(config, "tts_speed", 1.0))
        num_step_to_use = int(num_step if num_step is not None else getattr(config, "tts_num_step", 32))
        guidance_scale_to_use = float(guidance_scale if guidance_scale is not None else getattr(config, "tts_guidance_scale", 2.0))
        seed_to_use = int(seed if seed is not None else getattr(config, "tts_seed", 42))

        # Check Cache
        cache_key = self._compute_cache_key(
            text, voice_to_use, language_to_use, speed_to_use,
            num_step_to_use, guidance_scale_to_use, format_to_use, seed_to_use
        )
        if cache_key in self._cache:
            logger.info(f"⚡ TTS Cache HIT for '{text[:25]}...'")
            return self._cache[cache_key]

        payload = {
            "text": text,
            "voice": voice_to_use,
            "language": language_to_use,
            "speed": speed_to_use,
            "num_step": num_step_to_use,
            "guidance_scale": guidance_scale_to_use,
            "response_format": format_to_use,
            "seed": seed_to_use
        }

        url = self.base_url
        if not url.endswith("/api/v1/tts") and "/api/v1/tts" not in url:
            if "/api/tts" in url:
                url = url.replace("/api/tts", "/api/v1/tts")
            else:
                url = f"{url}/api/v1/tts"

        headers = {"Content-Type": "application/json"}
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Requesting TTS API (attempt {attempt}/{max_retries}): {url} | text='{text[:30]}...' | voice={voice_to_use}")

                if method.upper() == "GET":
                    response = requests.get(url, params=payload, timeout=timeout)
                else:
                    response = requests.post(url, json=payload, headers=headers, timeout=timeout)

                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    data = response.json()
                    b64_audio = data.get("audio") or data.get("data") or data.get("audio_base64") or data.get("speech")
                    if not b64_audio:
                        raise ValueError(f"No audio key found in JSON response: {list(data.keys())}")
                    audio_bytes = base64.b64decode(b64_audio)
                    mime_type = data.get("mime_type", f"audio/{format_to_use}")
                else:
                    audio_bytes = response.content
                    if "ogg" in content_type or format_to_use in ("ogg", "opus"):
                        mime_type = "audio/ogg"
                    elif "mp3" in content_type or format_to_use == "mp3" or "mpeg" in content_type:
                        mime_type = "audio/mpeg"
                    elif "flac" in content_type or format_to_use == "flac":
                        mime_type = "audio/flac"
                    elif "wav" in content_type or format_to_use == "wav":
                        mime_type = "audio/wav"
                    else:
                        mime_type = content_type if content_type else f"audio/{format_to_use}"

                if len(self._cache) >= self._max_cache_entries:
                    first_key = next(iter(self._cache))
                    del self._cache[first_key]
                self._cache[cache_key] = (audio_bytes, mime_type)

                return audio_bytes, mime_type

            except Exception as e:
                last_exception = e
                logger.warning(f"TTS API attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    time.sleep(0.5 * attempt)

        raise RuntimeError(f"Local TTS API failed after {max_retries} attempts: {last_exception}") from last_exception

# Default instance
tts_client = TTSClient()
