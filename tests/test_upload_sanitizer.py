import unittest
from app.sanitizer import (
    validate_and_sanitize_audio_upload,
    verify_streamer_password,
    MAX_AUDIO_UPLOAD_SIZE,
)


class TestUploadSanitizer(unittest.TestCase):

    def test_valid_mp3_header_id3(self):
        # ID3 header + dummy bytes
        mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 100
        sound_name, filename = validate_and_sanitize_audio_upload(mp3_bytes, "Boom_Sound!.mp3")
        self.assertEqual(sound_name, "boom_sound")
        self.assertEqual(filename, "boom_sound.mp3")

    def test_valid_wav_header(self):
        # RIFF ... WAVE header
        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 50
        sound_name, filename = validate_and_sanitize_audio_upload(wav_bytes, "Bruh-123.wav")
        self.assertEqual(sound_name, "bruh-123")
        self.assertEqual(filename, "bruh-123.wav")

    def test_valid_ogg_header(self):
        ogg_bytes = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00" + b"\x00" * 50
        sound_name, filename = validate_and_sanitize_audio_upload(ogg_bytes, "fart.ogg")
        self.assertEqual(sound_name, "fart")
        self.assertEqual(filename, "fart.ogg")

    def test_valid_flac_header(self):
        flac_bytes = b"fLaC\x00\x00\x00\x22" + b"\x00" * 50
        sound_name, filename = validate_and_sanitize_audio_upload(flac_bytes, "airhorn.flac")
        self.assertEqual(sound_name, "airhorn")
        self.assertEqual(filename, "airhorn.flac")

    def test_valid_m4a_header(self):
        m4a_bytes = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + b"\x00" * 50
        sound_name, filename = validate_and_sanitize_audio_upload(m4a_bytes, "cheer.m4a")
        self.assertEqual(sound_name, "cheer")
        self.assertEqual(filename, "cheer.m4a")

    def test_invalid_magic_bytes_rejected(self):
        # Fake MP3 file with HTML/script content
        fake_bytes = b"<html><script>alert(1)</script></html>"
        with self.assertRaises(ValueError) as ctx:
            validate_and_sanitize_audio_upload(fake_bytes, "exploit.mp3")
        self.assertIn("does not match a valid MP3", str(ctx.exception))

    def test_invalid_extension_rejected(self):
        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        with self.assertRaises(ValueError) as ctx:
            validate_and_sanitize_audio_upload(wav_bytes, "script.exe")
        self.assertIn("Unsupported file extension", str(ctx.exception))

    def test_oversized_file_rejected(self):
        big_bytes = b"ID3" + (b"\x00" * (MAX_AUDIO_UPLOAD_SIZE + 1))
        with self.assertRaises(ValueError) as ctx:
            validate_and_sanitize_audio_upload(big_bytes, "big.mp3")
        self.assertIn("exceeds maximum allowed size", str(ctx.exception))

    def test_path_traversal_filename_sanitized(self):
        mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 100
        sound_name, filename = validate_and_sanitize_audio_upload(mp3_bytes, "../../etc/passwd..mp3")
        self.assertEqual(sound_name, "etcpasswd")
        self.assertEqual(filename, "etcpasswd.mp3")

    def test_verify_streamer_password(self):
        active = ["Shroud", "summit1g"]
        self.assertTrue(verify_streamer_password("shroud", active))
        self.assertTrue(verify_streamer_password("SUMMIT1G", active))
        self.assertFalse(verify_streamer_password("wrong_password", active))
        self.assertFalse(verify_streamer_password("", active))


if __name__ == "__main__":
    unittest.main()
