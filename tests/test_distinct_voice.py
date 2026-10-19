import os
import sys
import unittest

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.voice_effects import (
    apply_distinct_user_voice,
    describe_user_voice,
    user_semitone_offset,
    user_vertical_mode,
)


def _make_wav(seconds=0.5, rate=44100):
    import math
    import struct
    n = int(seconds * rate)
    frames = b"".join(
        struct.pack("<h", int(10000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n)
    )
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


class TestDistinctVoice(unittest.TestCase):

    def test_offset_deterministic_and_bounded(self):
        for user in ["alice", "Bob", "m_e_s_t_a_a_j_a", "xX_gamer_Xx"]:
            a = user_semitone_offset(user, 7.0)
            b = user_semitone_offset(user.upper(), 7.0)
            self.assertEqual(a, b)
            self.assertGreaterEqual(abs(a), 1.5)
            self.assertLessEqual(abs(a), 7.0)

    def test_offset_respects_span(self):
        for user in ["alice", "bob", "carol", "dave"]:
            o = user_semitone_offset(user, 3.0)
            self.assertLessEqual(abs(o), 3.0)

    def test_different_users_differ(self):
        offsets = {user_semitone_offset(f"user{i:03d}", 7.0) for i in range(20)}
        # 20 users must not all collapse onto one key
        self.assertGreater(len(offsets), 3)

    def test_vertical_deterministic(self):
        self.assertEqual(user_vertical_mode("alice"), user_vertical_mode("ALICE"))
        self.assertIn(user_vertical_mode("alice"), ("above", "below"))

    def test_describe_label(self):
        d = describe_user_voice("alice", 7.0)
        self.assertIn("semitones", d)
        self.assertIn(d["vertical"], ("above", "below"))
        self.assertIn("st/", d["label"])

    def test_apply_changes_audio(self):
        wav = _make_wav()
        out, mime = apply_distinct_user_voice(wav, "wav", username="alice", span=7.0, vertical=True)
        self.assertTrue(mime.startswith("audio/"))
        self.assertNotEqual(out, wav)
        self.assertGreater(len(out), 1000)

    def test_apply_stable_per_user(self):
        wav = _make_wav()
        out1, _ = apply_distinct_user_voice(wav, "wav", username="bob", span=7.0, vertical=True)
        out2, _ = apply_distinct_user_voice(wav, "wav", username="bob", span=7.0, vertical=True)
        self.assertEqual(out1, out2)

    def test_apply_empty_username_passthrough(self):
        wav = _make_wav()
        out, _ = apply_distinct_user_voice(wav, "wav", username="", span=7.0, vertical=True)
        self.assertEqual(out, wav)


if __name__ == "__main__":
    unittest.main()
