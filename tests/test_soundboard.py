import os
import tempfile
import unittest
from app.config import config
from app.soundboard import SoundboardManager, soundboard_manager
from app.text_chunker import process_message_to_chunks


class TestSoundboard(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.sb_manager = SoundboardManager(soundboard_dir=self.test_dir.name)
        
        # Create dummy sound files
        self.boom_file = os.path.join(self.test_dir.name, "boom.mp3")
        with open(self.boom_file, "wb") as f:
            f.write(b"fake_mp3_data_boom")

        self.bruh_file = os.path.join(self.test_dir.name, "bruh.wav")
        with open(self.bruh_file, "wb") as f:
            f.write(b"fake_wav_data_bruh")

        self.airhorn_file = os.path.join(self.test_dir.name, "airhorn.ogg")
        with open(self.airhorn_file, "wb") as f:
            f.write(b"fake_ogg_data_airhorn")

    def tearDown(self):
        self.test_dir.cleanup()

    def test_get_available_sounds(self):
        sounds = self.sb_manager.get_available_sounds()
        self.assertIn("boom", sounds)
        self.assertIn("bruh", sounds)
        self.assertIn("airhorn", sounds)
        self.assertEqual(sounds["boom"], self.boom_file)

    def test_find_sound_exact(self):
        match = self.sb_manager.find_sound("boom")
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "boom")
        self.assertEqual(match[1], self.boom_file)

        # Case-insensitive
        match_caps = self.sb_manager.find_sound("BOOM")
        self.assertIsNotNone(match_caps)
        self.assertEqual(match_caps[0], "boom")

    def test_find_sound_fuzzy_rapidfuzz(self):
        # Fuzzy match boooom -> boom
        match_fuzzy = self.sb_manager.find_sound("boooom")
        self.assertIsNotNone(match_fuzzy)
        self.assertEqual(match_fuzzy[0], "boom")

        # Fuzzy match bruhh -> bruh
        match_bruh = self.sb_manager.find_sound("bruhh")
        self.assertIsNotNone(match_bruh)
        self.assertEqual(match_bruh[0], "bruh")

    def test_find_sound_no_match(self):
        match = self.sb_manager.find_sound("xyz123nonexistent")
        self.assertIsNone(match)

    def test_parse_soundboard_text(self):
        text = "Hello (boom) welcome to (bruh) stream"
        segments = self.sb_manager.parse_soundboard_text(text)

        self.assertEqual(len(segments), 5)
        self.assertEqual(segments[0]["type"], "text")
        self.assertEqual(segments[0]["content"], "Hello ")

        self.assertEqual(segments[1]["type"], "soundboard")
        self.assertEqual(segments[1]["sound_name"], "boom")

        self.assertEqual(segments[2]["type"], "text")
        self.assertEqual(segments[2]["content"], " welcome to ")

        self.assertEqual(segments[3]["type"], "soundboard")
        self.assertEqual(segments[3]["sound_name"], "bruh")

        self.assertEqual(segments[4]["type"], "text")
        self.assertEqual(segments[4]["content"], " stream")

    def test_process_message_to_chunks_with_soundboard(self):
        orig_dir = config.soundboard_dir
        config.soundboard_dir = self.test_dir.name
        try:
            text = "Testing (boom) and sound [alice] (bruh) end"
            chunks = process_message_to_chunks(text)

            sb_chunks = [c for c in chunks if c.is_soundboard]
            self.assertEqual(len(sb_chunks), 2)
            self.assertEqual(sb_chunks[0].sound_name, "boom")
            self.assertEqual(sb_chunks[1].sound_name, "bruh")
            self.assertEqual(sb_chunks[1].sound_file, self.bruh_file)
            self.assertEqual(sb_chunks[1].voice, "alice")
        finally:
            config.soundboard_dir = orig_dir

    def test_permission_fallback(self):
        # Point to a restricted system path where normal user cannot create directories
        restricted_mgr = SoundboardManager(soundboard_dir="/root/restricted_soundboard_test_dir")
        accessible = restricted_mgr.get_accessible_directories()
        self.assertTrue(len(accessible) > 0)
        # Verify fallback directory is accessible and writable
        fallback_dir = accessible[0]
        self.assertTrue(os.path.exists(fallback_dir))
        self.assertTrue(os.access(fallback_dir, os.W_OK))


if __name__ == "__main__":
    unittest.main()
