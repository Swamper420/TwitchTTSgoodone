import json
import unittest
from unittest.mock import MagicMock, patch
from app.chat_commands import get_commands_catalog
from app.sanitizer import validate_and_sanitize_audio_upload, verify_streamer_password


class TestViewerEndpoints(unittest.TestCase):

    def test_commands_catalog_structure(self):
        catalog = get_commands_catalog()
        self.assertIsInstance(catalog, list)
        self.assertGreater(len(catalog), 0)

        for cmd in catalog:
            self.assertIn("name", cmd)
            self.assertIn("category", cmd)
            self.assertIn("syntax", cmd)
            self.assertIn("description", cmd)
            self.assertIn("aliases", cmd)

    def test_upload_payload_sanitization(self):
        mp3_header = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 100
        sound_name, filename = validate_and_sanitize_audio_upload(mp3_header, "TestSound.mp3", custom_sound_name="Air_Horn")
        self.assertEqual(sound_name, "air_horn")
        self.assertEqual(filename, "air_horn.mp3")

    def test_streamer_password_check(self):
        active_channels = ["Shroud", "summit1g"]
        self.assertTrue(verify_streamer_password("shroud", active_channels))
        self.assertTrue(verify_streamer_password("summit1g", active_channels))
        self.assertFalse(verify_streamer_password("random_viewer", active_channels))


if __name__ == "__main__":
    unittest.main()
