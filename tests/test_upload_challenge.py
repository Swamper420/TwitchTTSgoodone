import unittest
from app.upload_challenge import UploadChallengeManager
from app.server import extract_upload_token


def legit_solution(challenge, start_ms=600, gap_ms=800):
    tids = [t["tid"] for t in challenge["payload"]["targets"]]
    events = [{"tid": t, "t": start_ms + i * gap_ms} for i, t in enumerate(tids)]
    return {"hits": list(tids), "events": events,
            "duration_ms": start_ms + len(tids) * gap_ms}


class TestUploadChallenge(unittest.TestCase):

    def test_mission_varies_every_time(self):
        m = UploadChallengeManager()
        layouts = set()
        for _ in range(10):
            c = m.create_challenge("1.2.3.4")
            self.assertTrue(c["success"])
            self.assertEqual(c["challenge_type"], "headcrab_aim")
            p = c["payload"]
            self.assertEqual(p["w"], 480)
            self.assertEqual(p["h"], 270)
            self.assertTrue(6 <= p["required_hits"] <= 9)
            self.assertTrue(3 <= len(p["decoys"]) <= 5)
            self.assertEqual(len(p["targets"]), p["required_hits"])
            layouts.add(tuple(sorted((t["x"], t["y"]) for t in p["targets"])))
        self.assertEqual(len(layouts), 10)

    def test_hit_log_roundtrip_single_use(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", tuning={"min_duration_ms": 0})
        ok, res = m.verify_solution(c["challenge_id"], legit_solution(c), "1.2.3.4")
        self.assertTrue(ok, res)
        ok2, _ = m.peek_upload_token(res["upload_token"], "1.2.3.4")
        self.assertTrue(ok2)
        m.burn_upload_token(res["upload_token"])
        ok3, err = m.peek_upload_token(res["upload_token"], "1.2.3.4")
        self.assertFalse(ok3)
        self.assertIn("already used", err)

    def test_instant_submit_rejected(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4")
        ok, res = m.verify_solution(c["challenge_id"], legit_solution(c, 0, 0), "1.2.3.4")
        self.assertFalse(ok)
        self.assertIn("humanly possible", res["error"])

    def test_spray_timing_rejected(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", tuning={"min_duration_ms": 0})
        ok, res = m.verify_solution(c["challenge_id"], legit_solution(c, 100, 10), "1.2.3.4")
        self.assertFalse(ok)
        self.assertIn("aimbot", res["error"])

    def test_forged_and_decoy_hits_rejected(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", tuning={"min_duration_ms": 0})
        sol = legit_solution(c)
        sol["hits"][0] = "forged-tid"
        ok, _ = m.verify_solution(c["challenge_id"], sol, "1.2.3.4")
        self.assertFalse(ok)

        c = m.create_challenge("1.2.3.4", tuning={"min_duration_ms": 0})
        sol = legit_solution(c)
        sol["hits"][-1] = c["payload"]["decoys"][0]["tid"]
        ok, res = m.verify_solution(c["challenge_id"], sol, "1.2.3.4")
        self.assertFalse(ok)
        self.assertIn("Friendly fire", res["error"])

    def test_attempt_limit_burns_challenge(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", tuning={"min_duration_ms": 0})
        bad = {"hits": ["nope"], "events": []}
        for _ in range(5):
            ok, _ = m.verify_solution(c["challenge_id"], bad, "1.2.3.4")
            self.assertFalse(ok)
        ok, res = m.verify_solution(c["challenge_id"], bad, "1.2.3.4")
        self.assertFalse(ok)
        self.assertIn("expired or not found", res["error"])

    def test_ip_binding(self):
        m = UploadChallengeManager()
        c = m.create_challenge("1.2.3.4", tuning={"min_duration_ms": 0})
        ok, res = m.verify_solution(c["challenge_id"], legit_solution(c), "9.9.9.9")
        self.assertFalse(ok)
        self.assertIn("different network", res["error"])

    def test_extract_upload_token(self):
        self.assertEqual(extract_upload_token({}, b"", {"upload_token": "abc"}), "abc")
        headers = {"Content-Type": "application/json", "X-Upload-Token": "hdr-tok"}
        self.assertEqual(extract_upload_token(headers, b"", {}), "hdr-tok")
        self.assertEqual(extract_upload_token({}, b"", {}), "")


if __name__ == "__main__":
    unittest.main()
