import os
import struct
import tempfile
import unittest
import wave
from unittest.mock import patch, MagicMock

from app import audio_norm
from app.audio_norm import (
    normalize_audio_bytes,
    normalize_audio_file_inplace,
    normalize_all_soundboard_files,
    is_ffmpeg_available,
)
from app.config import config


def make_wav_bytes(duration_s=0.5, freq=440, volume=0.9, rate=44100):
    import math
    n = int(duration_s * rate)
    buf = bytearray()
    for i in range(n):
        s = int(volume * 32767 * math.sin(2 * math.pi * freq * i / rate))
        buf += struct.pack("<h", max(-32768, min(32767, s)))
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    try:
        with wave.open(tmp.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(buf))
        with open(tmp.name, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass


class TestAudioNorm(unittest.TestCase):
    def test_disabled_returns_original(self):
        orig = make_wav_bytes(volume=0.9)
        prev = config.enable_audio_norm
        config.enable_audio_norm = False
        try:
            out, mime = normalize_audio_bytes(orig, audio_format="wav")
            self.assertEqual(out, orig)
            self.assertIn("audio", mime)
        finally:
            config.enable_audio_norm = prev

    def test_enabled_normalizes_real_ffmpeg(self):
        if not is_ffmpeg_available():
            self.skipTest("ffmpeg not available")
        prev = config.enable_audio_norm
        config.enable_audio_norm = True
        try:
            loud = make_wav_bytes(volume=0.9)
            quiet = make_wav_bytes(volume=0.05)
            loud_out, _ = normalize_audio_bytes(loud, audio_format="wav")
            quiet_out, _ = normalize_audio_bytes(quiet, audio_format="wav")
            # Both should still be valid wav bytes
            self.assertTrue(len(loud_out) > 1000)
            self.assertTrue(len(quiet_out) > 1000)
            # Quiet file should get boosted (normalized output larger RMS than input).
            # Compare raw PCM energy roughly: decode and check max amplitude grew.
            def max_amp(data):
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
                        t.write(data)
                        p = t.name
                    with wave.open(p, "rb") as w:
                        frames = w.readframes(w.getnframes())
                    os.remove(p)
                    amps = struct.unpack(f"<{len(frames)//2}h", frames)
                    return max(abs(a) for a in amps) if amps else 0
                except Exception:
                    return 0
            self.assertGreater(max_amp(quiet_out), max_amp(quiet))
        finally:
            config.enable_audio_norm = prev

    def test_ffmpeg_failure_falls_back(self):
        orig = make_wav_bytes(volume=0.5)
        prev = config.enable_audio_norm
        config.enable_audio_norm = True
        try:
            with patch("app.audio_norm.is_ffmpeg_available", return_value=False):
                out, _ = normalize_audio_bytes(orig, audio_format="wav")
                self.assertEqual(out, orig)
            with patch("subprocess.run", side_effect=RuntimeError("boom")):
                out, _ = normalize_audio_bytes(orig, audio_format="wav")
                self.assertEqual(out, orig)
        finally:
            config.enable_audio_norm = prev

    def test_normalize_file_inplace(self):
        if not is_ffmpeg_available():
            self.skipTest("ffmpeg not available")
        d = tempfile.TemporaryDirectory()
        try:
            p = os.path.join(d.name, "quiet.wav")
            with open(p, "wb") as f:
                f.write(make_wav_bytes(volume=0.05))
            before = os.path.getsize(p)
            self.assertTrue(normalize_audio_file_inplace(p))
            self.assertTrue(os.path.exists(p))
            self.assertGreater(os.path.getsize(p), 1000)
            self.assertNotEqual(os.path.getsize(p), 0)
            self.assertTrue(before > 0)
        finally:
            d.cleanup()

    def test_normalize_all_soundboard_files_empty(self):
        from app.soundboard import SoundboardManager
        d = tempfile.TemporaryDirectory()
        try:
            mgr = SoundboardManager(soundboard_dir=d.name)
            with patch.object(mgr, "get_available_sounds", return_value={}):
                with patch("app.soundboard.soundboard_manager", mgr):
                    result = normalize_all_soundboard_files()
                    self.assertEqual(result["total"], 0)
                    self.assertEqual(result["ok"], 0)
        finally:
            d.cleanup()

    def test_finalize_audio_in_server(self):
        from app.server import finalize_audio
        orig = make_wav_bytes(volume=0.5)
        out, mime = finalize_audio(orig, audio_format="wav")
        self.assertTrue(isinstance(out, bytes))
        self.assertIn("audio", mime)


if __name__ == "__main__":
    unittest.main()
