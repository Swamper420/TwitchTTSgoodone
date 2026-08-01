import base64
import hashlib
import logging
import time
import urllib.parse
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
        
    def _compute_cache_key(self, text: str, voice: Optional[str], model: Optional[str], fmt: str) -> str:
        key_str = f"{text}|{voice or ''}|{model or ''}|{fmt}"
        return hashlib.sha256(key_str.encode('utf-8')).hexdigest()
        
    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        audio_format: Optional[str] = None,
        method: str = "POST",
        timeout: float = 45.0,
        max_retries: int = 3
    ) -> Tuple[bytes, str]:
        """
        Synthesize text to audio.
        Returns tuple of (audio_bytes, mime_type).
        """
        raw_voice = voice or config.tts_voice
        raw_model = model or config.tts_model
        raw_format = audio_format or config.tts_format or "wav"

        voice_to_use = sanitize_identifier(raw_voice, max_len=100) if raw_voice else ""
        model_to_use = sanitize_identifier(raw_model, max_len=100) if raw_model else ""
        format_to_use = sanitize_audio_format(raw_format, default="wav")
        
        # Ensure text meets minimum character threshold to avoid API blocking short requests
        min_chars = config.min_chunk_chars
        if text and len(text) < min_chars:
            while len(text) < min_chars:
                text = text + "bruhbruh"
        elif not text:
            text = "bruhbruh"
            while len(text) < min_chars:
                text = text + "bruhbruh"
        
        # Check Cache
        cache_key = self._compute_cache_key(text, voice_to_use, model_to_use, format_to_use)
        if cache_key in self._cache:
            logger.info(f"⚡ TTS Cache HIT for '{text[:25]}...'")
            return self._cache[cache_key]
            
        params: Dict[str, Any] = {"text": text}
        if voice_to_use:
            params["voice"] = voice_to_use
        if model_to_use:
            params["model"] = model_to_use
        if format_to_use:
            params["format"] = format_to_use
            
        url = self.base_url
        if not url.endswith("/api/tts") and not "/api/tts" in url:
            url = f"{url}/api/tts"
            
        headers = {}
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Requesting TTS API (attempt {attempt}/{max_retries}): {url} | text='{text[:30]}...' | voice={voice_to_use}")
                
                if method.upper() == "GET":
                    response = requests.get(url, params=params, timeout=timeout)
                else:
                    headers["Content-Type"] = "application/json"
                    response = requests.post(url, json=params, headers=headers, timeout=timeout)
                    
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                
                # Case 1: JSON response containing base64 audio
                if "application/json" in content_type or format_to_use == "json":
                    data = response.json()
                    b64_audio = data.get("audio") or data.get("data") or data.get("audio_base64") or data.get("speech")
                    if not b64_audio:
                        raise ValueError(f"No audio key found in JSON response: {list(data.keys())}")
                    audio_bytes = base64.b64decode(b64_audio)
                    mime_type = data.get("mime_type", "audio/wav")
                else:
                    # Case 2: Binary audio stream (wav, ogg, pcm)
                    audio_bytes = response.content
                    if "ogg" in content_type or format_to_use in ("ogg", "opus"):
                        mime_type = "audio/ogg"
                    elif "wav" in content_type or format_to_use == "wav":
                        mime_type = "audio/wav"
                    elif "pcm" in content_type or format_to_use == "pcm":
                        mime_type = "audio/pcm"
                    else:
                        mime_type = content_type if content_type else "audio/wav"

                # Store in cache
                if len(self._cache) >= self._max_cache_entries:
                    first_key = next(iter(self._cache))
                    del self._cache[first_key]
                self._cache[cache_key] = (audio_bytes, mime_type)
                
                return audio_bytes, mime_type
                
            except Exception as e:
                last_exception = e
                logger.warning(f"TTS API attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    time.sleep(0.5 * attempt) # Exponential backoff

        raise RuntimeError(f"Local TTS API failed after {max_retries} attempts: {last_exception}") from last_exception

# Default instance
tts_client = TTSClient()
