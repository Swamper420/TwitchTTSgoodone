import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.sanitizer import (
    sanitize_string,
    sanitize_username,
    sanitize_identifier,
    sanitize_int,
    sanitize_bool,
    sanitize_audio_format,
    sanitize_url,
)


class TestSanitizer(unittest.TestCase):

    def test_sanitize_string(self):
        self.assertEqual(sanitize_string(None), "")
        self.assertEqual(sanitize_string("  hello world  "), "hello world")
        # Control characters and null bytes removed
        self.assertEqual(sanitize_string("hello\x00\x07world"), "helloworld")
        # Max length truncation
        self.assertEqual(sanitize_string("1234567890", max_len=5), "12345")
        # Non-string types safely converted
        self.assertEqual(sanitize_string(12345), "12345")

    def test_sanitize_username(self):
        self.assertEqual(sanitize_username("@TwitchUser123"), "twitchuser123")
        self.assertEqual(sanitize_username("#channel_name"), "channel_name")
        self.assertEqual(sanitize_username("valid_user"), "valid_user")
        # Invalid usernames with special symbols return empty string
        self.assertEqual(sanitize_username("invalid<user>!"), "")
        self.assertEqual(sanitize_username("user with spaces"), "")

    def test_sanitize_identifier(self):
        self.assertEqual(sanitize_identifier("voice-name_1.0"), "voice-name_1.0")
        self.assertEqual(sanitize_identifier("voice<script>alert(1)</script>"), "voicescriptalert1script")
        self.assertEqual(sanitize_identifier("", default="default_voice"), "default_voice")

    def test_sanitize_int(self):
        self.assertEqual(sanitize_int("100", default=10), 100)
        self.assertEqual(sanitize_int("invalid", default=50), 50)
        self.assertEqual(sanitize_int(None, default=50), 50)
        # Clamping
        self.assertEqual(sanitize_int(5, default=10, min_val=10, max_val=100), 10)
        self.assertEqual(sanitize_int(500, default=10, min_val=10, max_val=100), 100)

    def test_sanitize_bool(self):
        self.assertTrue(sanitize_bool(True))
        self.assertFalse(sanitize_bool(False))
        self.assertTrue(sanitize_bool("true"))
        self.assertTrue(sanitize_bool("YES"))
        self.assertTrue(sanitize_bool(1))
        self.assertFalse(sanitize_bool("off"))
        self.assertFalse(sanitize_bool(0))

    def test_sanitize_audio_format(self):
        self.assertEqual(sanitize_audio_format("wav"), "wav")
        self.assertEqual(sanitize_audio_format("MP3"), "mp3")
        self.assertEqual(sanitize_audio_format("ogg"), "ogg")
        self.assertEqual(sanitize_audio_format("flac"), "flac")
        self.assertEqual(sanitize_audio_format("json"), "json")
        # Unsupported formats fallback to default
        self.assertEqual(sanitize_audio_format("exe"), "wav")
        self.assertEqual(sanitize_audio_format("invalid_format"), "wav")

    def test_sanitize_url(self):
        self.assertEqual(sanitize_url("http://localhost:8880/"), "http://localhost:8880")
        self.assertEqual(sanitize_url("https://api.elevenlabs.io"), "https://api.elevenlabs.io")
        self.assertEqual(sanitize_url("javascript:alert(1)", default="http://localhost:8880"), "http://localhost:8880")


if __name__ == "__main__":
    unittest.main()
