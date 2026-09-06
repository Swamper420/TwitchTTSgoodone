import unittest
from app.upload_challenge import UploadChallengeManager
from app.server import extract_upload_token


class TestUploadChallenge(unittest.TestCase):

    def test_variable_types(self):
        m = UploadChallengeManager()
        seen = set()
        for _ in range(30):
            c = m.create_challenge("1.2.3.4")
            self.assertTrue(c["success"])
            seen.add(c["challenge_type"])
        self.assertEqual(seen, {"hev_math", "lambda_memory", "headcrab_sweep"})

    def test_hev_math_single_use(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", forced_type="hev_math")
        a, b, op = c["payload"]["a"], c["payload"]["b"], c["payload"]["op"]
        expected = {"+": a + b, "-": a - b, "×": a * b}[op]
        ok, res = m.verify_solution(c["challenge_id"], {"answer": str(expected)}, "1.2.3.4")
        self.assertTrue(ok)
        ok2, _ = m.peek_upload_token(res["upload_token"], "1.2.3.4")
        self.assertTrue(ok2)
        m.burn_upload_token(res["upload_token"])
        ok3, err = m.peek_upload_token(res["upload_token"], "1.2.3.4")
        self.assertFalse(ok3)
        self.assertIn("already used", err)

    def test_attempt_limit_burns_challenge(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", forced_type="hev_math")
        for _ in range(5):
            ok, _ = m.verify_solution(c["challenge_id"], {"answer": "nope-zzz"}, "1.2.3.4")
            self.assertFalse(ok)
        ok, res = m.verify_solution(c["challenge_id"], {"answer": "nope-zzz"}, "1.2.3.4")
        self.assertFalse(ok)
        self.assertIn("expired or not found", res["error"])

    def test_ip_binding(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", forced_type="hev_math")
        ok, res = m.verify_solution(c["challenge_id"], {"answer": "0"}, "9.9.9.9")
        self.assertFalse(ok)
        self.assertIn("different network", res["error"])

    def test_lambda_and_sweep_roundtrip(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", forced_type="lambda_memory")
        ok, _ = m.verify_solution(c["challenge_id"], {"sequence": c["payload"]["sequence"]}, "1.2.3.4")
        self.assertTrue(ok)
        c = m.create_challenge("1.2.3.4", forced_type="headcrab_sweep")
        expected = sorted(i for i, g in enumerate(c["payload"]["grid"]) if g == c["payload"]["target"])
        ok, _ = m.verify_solution(c["challenge_id"], {"cells": expected}, "1.2.3.4")
        self.assertTrue(ok)

    def test_extract_upload_token(self):
        self.assertEqual(extract_upload_token({}, b"", {"upload_token": "abc"}), "abc")
        headers = {"Content-Type": "application/json", "X-Upload-Token": "hdr-tok"}
        self.assertEqual(extract_upload_token(headers, b"", {}), "hdr-tok")
        self.assertEqual(extract_upload_token({}, b"", {}), "")


if __name__ == "__main__":
    unittest.main()
