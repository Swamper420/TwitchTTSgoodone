"""Half-Life 2 aim-trainer upload gate: server-verified canvas shooting minigame.

Security model (cannot be bypassed by calling /api/soundboard/upload directly):
  1. Client requests a challenge -> server creates a randomized shooting range
     (random target positions/sizes/speeds, random decoys, random time limit)
     and stores the expected answer ONLY server-side (in-memory).
  2. The player aims with the mouse and shoots every headcrab (tid-identified)
     without hitting friendlies, against the clock, in the viewer canvas game.
  3. On a clean win the client submits the hit log. The server verifies:
       - the submitted target ids EXACTLY match the issued set
         (ids are unguessable 64-bit secrets — spraying/forging fails),
       - no decoy id is present,
       - per-shot timestamps are monotonic, human-plausible
         (min gap between aimed shots kills click-spray scripts),
       - total elapsed time (server clock) is above a per-challenge minimum
         (instant-submit bots fail) and inside the mission window.
     On success it issues a single-use, IP-bound, short-lived upload token.
  4. /api/soundboard/upload REQUIRES a valid, unused upload token and consumes
     it on success. One completed mission == exactly one uploaded file.

Anti-automation / anti-replay properties:
  - challenge_id and upload_token are secrets.token_urlsafe values.
  - target/decoy ids are unguessable; the full hit set cannot be derived
    without actually receiving (and solving) the issued challenge.
  - Challenges expire after CHALLENGE_TTL_SECONDS (default 5 min).
  - Upload tokens expire after UPLOAD_TOKEN_TTL_SECONDS (default 10 min),
    are single-use, and are bound to the requesting client IP.
  - Max MAX_VERIFY_ATTEMPTS wrong submissions per challenge, then the
    challenge is invalidated and a new mission must be requested.
  - Every mission is freshly randomized (positions, sizes, drift, counts,
    time limit, backdrop) so it is never the same twice.
"""

import random
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

CHALLENGE_TTL_SECONDS = 5 * 60
UPLOAD_TOKEN_TTL_SECONDS = 10 * 60
MAX_VERIFY_ATTEMPTS = 5

# Logical canvas size the browser game renders (CSS scales it).
CANVAS_W = 480
CANVAS_H = 270

# Friendly-fire decoys: shooting one costs a life in the browser game.
DECOY_KINDS = [
    {"kind": "combine", "icon": "⬢", "label": "Combine Soldier"},
    {"kind": "scanner", "icon": "🛸", "label": "City Scanner"},
    {"kind": "citizen", "icon": "🧍", "label": "Citizen"},
    {"kind": "vort", "icon": "👁", "label": "Vortigaunt"},
]

TARGET_ICON = "🦀"
TARGET_LABEL = "Headcrab"

# Verification bounds.
MIN_MS_PER_HIT = 350        # total elapsed must be >= hits * this (kills instant bots)
MIN_MS_BETWEEN_SHOTS = 90   # per-shot gaps below this look like a spray script
VERIFY_GRACE_SECONDS = 15   # extra headroom past the mission timer for slow networks


class UploadChallengeManager:
    """Thread-safe store for aim-trainer challenges and single-use upload tokens."""

    def __init__(self):
        self._lock = threading.Lock()
        # challenge_id -> {type, target_ids, decoy_ids, required_hits,
        #                 created, min_duration_ms, time_limit_s, ip, attempts}
        self._challenges: Dict[str, Dict[str, Any]] = {}
        # upload_token -> {expires, ip, used}
        self._tokens: Dict[str, Dict[str, Any]] = {}

    # -- internals -----------------------------------------------------
    def _cleanup_locked(self) -> None:
        now = time.time()
        for cid in [k for k, v in self._challenges.items() if v.get("expires", 0) <= now]:
            del self._challenges[cid]
        for tok in [k for k, v in self._tokens.items() if v.get("expires", 0) <= now or v.get("used")]:
            entry = self._tokens[tok]
            if entry.get("expires", 0) <= now or (entry.get("used") and now - entry.get("used_at", now) > 60):
                del self._tokens[tok]

    @staticmethod
    def _scatter(count: int, taken: List[Tuple[float, float]], margin: int = 34,
                 min_dist: int = 46) -> List[Tuple[float, float]]:
        """Randomly place points inside the canvas with minimum separation."""
        pts: List[Tuple[float, float]] = []
        for _ in range(count):
            for _ in range(60):  # rejection sampling attempts
                x = random.uniform(margin, CANVAS_W - margin)
                y = random.uniform(margin + 8, CANVAS_H - margin)
                if all((x - px) ** 2 + (y - py) ** 2 >= min_dist ** 2 for px, py in taken + pts):
                    pts.append((x, y))
                    break
            else:  # keep playable even in the pathological case
                pts.append((random.uniform(margin, CANVAS_W - margin),
                            random.uniform(margin + 8, CANVAS_H - margin)))
        return pts

    # -- challenge creation --------------------------------------------
    def create_challenge(self, client_ip: str, forced_type: Optional[str] = None,
                         tuning: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new randomized aim-trainer mission bound to client_ip.

        `tuning` is a test-only hook to override randomized parameters.
        Returns the public payload (target ids are unguessable opaque tokens).
        """
        with self._lock:
            self._cleanup_locked()
            tuning = tuning or {}
            challenge_id = secrets.token_urlsafe(24)
            now = time.time()
            expires = now + CHALLENGE_TTL_SECONDS

            num_targets = int(tuning.get("num_targets", random.randint(6, 9)))
            num_decoys = int(tuning.get("num_decoys", random.randint(3, 5)))
            time_limit_s = int(tuning.get("time_limit_s",
                                          18 + num_targets * 2 + random.randint(0, 5)))
            min_duration_ms = int(tuning.get("min_duration_ms", num_targets * MIN_MS_PER_HIT))
            backdrop = tuning.get("backdrop", random.choice(["city17", "canals", "citadel"]))

            positions = self._scatter(num_targets + num_decoys, [])

            targets = []
            for i in range(num_targets):
                x, y = positions[i]
                targets.append({
                    "tid": secrets.token_urlsafe(8),
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "r": random.randint(13, 19),
                    "amp": round(random.uniform(6, 16), 1),      # wander radius (px)
                    "speed": round(random.uniform(0.6, 1.7), 2),  # wander speed
                    "phase": round(random.uniform(0, 6.28), 2),
                    "icon": TARGET_ICON,
                    "label": TARGET_LABEL,
                })

            decoys = []
            for i in range(num_decoys):
                x, y = positions[num_targets + i]
                kind = random.choice(DECOY_KINDS)
                decoys.append({
                    "tid": secrets.token_urlsafe(8),
                    "x": round(x, 1),
                    "y": round(y, 1),
                    "r": random.randint(13, 18),
                    "amp": round(random.uniform(3, 9), 1),
                    "speed": round(random.uniform(0.3, 0.8), 2),
                    "phase": round(random.uniform(0, 6.28), 2),
                    "icon": kind["icon"],
                    "label": kind["label"],
                    "kind": kind["kind"],
                })

            self._challenges[challenge_id] = {
                "type": "headcrab_aim",
                "target_ids": {t["tid"] for t in targets},
                "decoy_ids": {d["tid"] for d in decoys},
                "required_hits": num_targets,
                "created": now,
                "expires": expires,
                "min_duration_ms": min_duration_ms,
                "time_limit_s": time_limit_s,
                "ip": client_ip,
                "attempts": 0,
            }

            return {
                "success": True,
                "challenge_id": challenge_id,
                "challenge_type": "headcrab_aim",
                "title": "HEADCRAB EXTERMINATION",
                "prompt": (
                    f"🎯 Ravenholm is overrun: neutralize all {num_targets} headcrabs "
                    f"with your mouse within {time_limit_s}s. Civilians, scanners and "
                    f"vortigaunts are friendly — friendly fire costs a life (3 lives)."
                ),
                "payload": {
                    "w": CANVAS_W,
                    "h": CANVAS_H,
                    "targets": targets,
                    "decoys": decoys,
                    "required_hits": num_targets,
                    "time_limit_s": time_limit_s,
                    "lives": 3,
                    "backdrop": backdrop,
                },
                "expires_in": CHALLENGE_TTL_SECONDS,
            }

    # -- verification ---------------------------------------------------
    def verify_solution(
        self, challenge_id: str, solution: Any, client_ip: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Verify a submitted hit log. On success returns (True, {upload_token...})."""
        if not challenge_id or not isinstance(challenge_id, str):
            return False, {"error": "Missing challenge_id. Start a new mission."}
        with self._lock:
            self._cleanup_locked()
            entry = self._challenges.get(challenge_id)
            if not entry:
                return False, {"error": "Mission expired or not found. Start a new one."}
            if entry.get("expires", 0) <= time.time():
                del self._challenges[challenge_id]
                return False, {"error": "Mission expired. Start a new one."}
            if entry.get("ip") and entry["ip"] != client_ip:
                return False, {"error": "Mission was issued to a different network address."}
            if entry.get("attempts", 0) >= MAX_VERIFY_ATTEMPTS:
                del self._challenges[challenge_id]
                return False, {"error": "Too many wrong attempts. Start a new mission."}

            if entry.get("type") != "headcrab_aim":
                return False, {"error": "Unknown mission type. Start a new one."}

            err = self._check_aim_solution(entry, solution)
            if err is not None:
                entry["attempts"] = entry.get("attempts", 0) + 1
                remaining = MAX_VERIFY_ATTEMPTS - entry["attempts"]
                if remaining <= 0:
                    del self._challenges[challenge_id]
                    return False, {"error": "Bogus after-action report — start a new mission."}
                return False, {
                    "error": err,
                    "attempts_remaining": remaining,
                }

            # Success: burn the challenge, mint a single-use upload token.
            del self._challenges[challenge_id]
            token = secrets.token_urlsafe(32)
            self._tokens[token] = {
                "expires": time.time() + UPLOAD_TOKEN_TTL_SECONDS,
                "ip": client_ip,
                "used": False,
            }
            return True, {
                "upload_token": token,
                "expires_in": UPLOAD_TOKEN_TTL_SECONDS,
                "message": "Clearance granted. One file upload authorized.",
            }

    def _check_aim_solution(self, entry: Dict[str, Any], solution: Any) -> Optional[str]:
        """Return None when the hit log is valid, else a human-readable error."""
        if not isinstance(solution, dict):
            return "Malformed after-action report. Play the mission for real."

        hits = solution.get("hits", solution.get("tids", []))
        events = solution.get("events", [])
        if not isinstance(hits, list) or not isinstance(events, list):
            return "Malformed after-action report. Play the mission for real."

        target_ids = entry["target_ids"]
        decoy_ids = entry["decoy_ids"]

        # 1. Exact target set, no decoys, no forgeries, no duplicates.
        if len(hits) != len(target_ids) or set(map(str, hits)) != set(target_ids):
            # Give a specific hint when friendly fire is in the log.
            if any(str(h) in decoy_ids for h in hits if isinstance(h, str)):
                return "Friendly fire detected in the report — civilians harmed. Mission failed."
            return "Hit log does not match the issued mission. Play it for real."

        # 2. Event log must cover every hit with sane per-shot timing.
        if len(events) != len(target_ids):
            return "Incomplete combat telemetry. Play the mission for real."
        try:
            ordered = sorted(events, key=lambda e: float(e["t"]))
            times = [float(e["t"]) for e in ordered]
            tids = [str(e["tid"]) for e in ordered]
        except (KeyError, TypeError, ValueError, AttributeError):
            return "Corrupt combat telemetry. Play the mission for real."
        if set(tids) != set(target_ids):
            return "Telemetry does not match reported hits. Play it for real."
        if any(t < 0 for t in times):
            return "Corrupt combat telemetry. Play the mission for real."
        for prev, cur in zip(times, times[1:]):
            if cur < prev:
                return "Corrupt combat telemetry. Play the mission for real."
            if cur - prev < MIN_MS_BETWEEN_SHOTS:
                return ("Shots fired faster than humanly possible — "
                        "Overwatch suspects an aimbot. Mission failed.")

        # 3. Server-clock bounds: too fast == scripted, too slow == expired.
        elapsed_ms = (time.time() - entry["created"]) * 1000.0
        if elapsed_ms < entry["min_duration_ms"]:
            return ("Mission completed faster than humanly possible — "
                    "Overwatch suspects automation. Play it for real.")
        if elapsed_ms > (entry["time_limit_s"] + VERIFY_GRACE_SECONDS) * 1000.0:
            return "Mission window expired. Start a new one."
        return None

    def consume_upload_token(self, token: Any, client_ip: str) -> Tuple[bool, str]:
        """Validate and burn a single-use upload token. Returns (ok, error)."""
        if not token or not isinstance(token, str):
            return False, "Minigame clearance required: complete the Black Mesa mission first."
        with self._lock:
            self._cleanup_locked()
            entry = self._tokens.get(token.strip())
            if not entry:
                return False, "Invalid or expired clearance token. Complete the mission again."
            if entry.get("expires", 0) <= time.time():
                del self._tokens[token.strip()]
                return False, "Clearance token expired. Complete the mission again."
            if entry.get("used"):
                return False, "Clearance token already used. Each file needs a fresh mission."
            if entry.get("ip") and entry["ip"] != client_ip:
                return False, "Clearance token was issued to a different network address."
            entry["used"] = True
            entry["used_at"] = time.time()
            return True, ""

    def peek_upload_token(self, token: Any, client_ip: str) -> Tuple[bool, str]:
        """Validate without consuming (lets failed file validation retry with same token)."""
        if not token or not isinstance(token, str):
            return False, "Minigame clearance required: complete the Black Mesa mission first."
        with self._lock:
            self._cleanup_locked()
            entry = self._tokens.get(token.strip())
            if not entry:
                return False, "Invalid or expired clearance token. Complete the mission again."
            if entry.get("expires", 0) <= time.time():
                return False, "Clearance token expired. Complete the mission again."
            if entry.get("used"):
                return False, "Clearance token already used. Each file needs a fresh mission."
            if entry.get("ip") and entry["ip"] != client_ip:
                return False, "Clearance token was issued to a different network address."
            return True, ""

    def burn_upload_token(self, token: Any) -> None:
        with self._lock:
            if isinstance(token, str) and token.strip() in self._tokens:
                self._tokens[token.strip()]["used"] = True
                self._tokens[token.strip()]["used_at"] = time.time()


upload_challenge_manager = UploadChallengeManager()
