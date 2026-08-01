import base64
import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple
import requests

from app.config import config

logger = logging.getLogger("TTSClient")

class TTSClient:
    """Client for local TTS API supporting GET and POST methods."""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or config.tts_api_url).rstrip('/')
        
    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        audio_format: Optional[str] = None,
        method: str = "POST",
        timeout: float = 15.0
    ) -> Tuple[bytes, str]:
        """
        Synthesize text to audio.
        Returns tuple of (audio_bytes, mime_type).
        """
        voice_to_use = voice or config.tts_voice
        model_to_use = model or config.tts_model
        format_to_use = audio_format or config.tts_format or "wav"
        
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
        
        logger.info(f"Requesting TTS API: {url} | text='{text[:30]}...' | voice={voice_to_use} | format={format_to_use}")
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, params=params, timeout=timeout)
            else:
                headers["Content-Type"] = "application/json"
                response = requests.post(url, json=params, headers=headers, timeout=timeout)
                
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "")
            
            # Case 1: JSON response containing base64 audio
            if "application/json" in content_type or format_to_use == "json":
                try:
                    data = response.json()
                    # Try common JSON payload keys
                    b64_audio = data.get("audio") or data.get("data") or data.get("audio_base64") or data.get("speech")
                    if not b64_audio:
                        raise ValueError(f"No audio key found in JSON response: {list(data.keys())}")
                    audio_bytes = base64.b64decode(b64_audio)
                    mime_type = data.get("mime_type", "audio/wav")
                    return audio_bytes, mime_type
                except Exception as e:
                    logger.error(f"Failed to decode JSON audio response: {e}")
                    raise
                    
            # Case 2: Binary audio stream (wav, ogg, pcm, etc.)
            audio_bytes = response.content
            
            # Determine MIME type
            if "ogg" in content_type or format_to_use in ("ogg", "opus"):
                mime_type = "audio/ogg"
            elif "wav" in content_type or format_to_use == "wav":
                mime_type = "audio/wav"
            elif "pcm" in content_type or format_to_use == "pcm":
                mime_type = "audio/pcm"
            else:
                mime_type = content_type if content_type else "audio/wav"
                
            return audio_bytes, mime_type
            
        except requests.exceptions.RequestException as e:
            logger.error(f"TTS API request failed for '{text}': {e}")
            raise RuntimeError(f"Local TTS API error: {e}") from e

# Default instance
tts_client = TTSClient()
