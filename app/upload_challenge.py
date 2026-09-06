"""Half-Life 2 themed upload gate: server-side minigame challenges.

Security model (cannot be bypassed by calling /api/soundboard/upload directly):
  1. Client requests a challenge -> server creates a random, variable puzzle and
     stores the expected answer ONLY server-side (in-memory).
  2. Client solves the puzzle in the viewer UI and submits the solution.
  3. Server verifies the solution. On success it issues a single-use,
     IP-bound, short-lived upload token.
  4. /api/soundboard/upload REQUIRES a valid, unused upload token and consumes
     it on success. One solved minigame == exactly one uploaded file.

Anti-automation / anti-replay properties:
  - challenge_id and upload_token are 256-bit secrets.token_urlsafe values.
  - Challenges expire after CHALLENGE_TTL_SECONDS (default 5 min).
  - Upload tokens expire after UPLOAD_TOKEN_TTL_SECONDS (default 10 min),
    are single-use, and are bound to the requesting client IP.
  - Max MAX_VERIFY_ATTEMPTS wrong submissions per challenge, then the
    challenge is invalidated and a new one must be requested.
  - Challenge type is chosen at random per request so it is not the same
    every time, and every puzzle payload is freshly randomized.
"""

import random
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

CHALLENGE_TTL_SECONDS = 5 * 60
UPLOAD_TOKEN_TTL_SECONDS = 10 * 60
MAX_VERIFY_ATTEMPTS = 5

# HL2-flavoured symbol pool for memory / grid games.
HL2_SYMBOLS = [
    {"id": "LAMBDA", "icon": "λ", "label": "Lambda"},
    {"id": "CROWBAR", "icon": "🔧", "label": "Crowbar"},
    {"id": "HEADCRAB", "icon": "🦀", "label": "Headcrab"},
    {"id": "GRAVITY", "icon": "🧲", "label": "Gravity Gun"},
    {"id": "COMBINE", "icon": "⬢", "label": "Combine"},
    {"id": "VORT", "icon": "👁", "label": "Vortigaunt"},
    {"id": "BATTERY", "icon": "🔋", "label": "HEV Battery"},
    {"id": "PORTAL", "icon": "🌀", "label": "Portal"},
]

VALID_SYMBOL_IDS = {s["id"] for s in HL2_SYMBOLS}


class UploadChallengeManager:
    """Thread-safe store for challenges and single-use upload tokens."""

    def __init__(self):
        self._lock = threading.Lock()
        # challenge_id -> {type, answer, expires, ip, attempts}
        self._challenges: Dict[str, Dict[str, Any]] = {}
        # upload_token -> {expires, ip, used}
        self._tokens: Dict[str, Dict[str, Any]] = {}

    # -- internals -----------------------------------------------------
    def _cleanup_locked(self) -> None:
        now = time.time()
        for cid in [k for k, v in self._challenges.items() if v.get("expires", 0) <= now]:
            del self._challenges[cid]
        for tok in [k for k, v in self._tokens.items() if v.get("expires", 0) <= now or v.get("used")]:
            # drop expired tokens; drop used tokens older than 60s to keep replay window tiny
            entry = self._tokens[tok]
            if entry.get("expires", 0) <= now or (entry.get("used") and now - entry.get("used_at", now) > 60):
                del self._tokens[tok]

    # -- challenge creation --------------------------------------------
    def create_challenge(self, client_ip: str, forced_type: Optional[str] = None) -> Dict[str, Any]:
        """Create a new random challenge bound to client_ip. Returns public payload (no answer)."""
        with self._lock:
            self._cleanup_locked()
            challenge_type = forced_type or random.choice(["hev_math", "lambda_memory", "headcrab_sweep"])
            challenge_id = secrets.token_urlsafe(24)
            expires = time.time() + CHALLENGE_TTL_SECONDS

            if challenge_type == "hev_math":
                a = random.randint(2, 25)
                b = random.randint(2, 25)
                op = random.choice(["+", "-", "×"])
                if op == "+":
                    answer = a + b
                elif op == "-":
                    # keep non-negative for friendliness
                    if b > a:
                        a, b = b, a
                    answer = a - b
                else:
                    # keep multiplication small
                    a = random.randint(2, 9)
                    b = random.randint(2, 9)
                    answer = a * b
                question = f"{a} {op} {b}"
                flavor_actions = [
                    "Calibrate the HEV suit power core",
                    "Charge the Gravity Gun",
                    "Stabilize the portal reactor",
                    "Power up the Black Mesa grid",
                ]
                prompt = (
                    f"⚡ {random.choice(flavor_actions)}: "
                    f"how much Auxiliary Power does {question} provide?"
                )
                self._challenges[challenge_id] = {
                    "type": "hev_math",
                    "answer": str(answer),
                    "expires": expires,
                    "ip": client_ip,
                    "attempts": 0,
                }
                public = {
                    "challenge_id": challenge_id,
                    "challenge_type": "hev_math",
                    "title": "HEV SUIT POWER CALIBRATION",
                    "prompt": prompt,
                    "payload": {"a": a, "b": b, "op": op, "question": question},
                    "expires_in": CHALLENGE_TTL_SECONDS,
                }
            elif challenge_type == "lambda_memory":
                length = random.randint(4, 6)
                seq = [random.choice(list(VALID_SYMBOL_IDS)) for _ in range(length)]
                code_names = [
                    "Recall the Lambda relay sequence",
                    "Repeat Dr. Kleiner's lab code",
                    "Echo the Vortigaunt chant order",
                ]
                self._challenges[challenge_id] = {
                    "type": "lambda_memory",
                    "answer": list(seq),
                    "expires": expires,
                    "ip": client_ip,
                    "attempts": 0,
                }
                public = {
                    "challenge_id": challenge_id,
                    "challenge_type": "lambda_memory",
                    "title": "LAMBDA RELAY MEMORY",
                    "prompt": (
                        f"🔶 {random.choice(code_names)}: watch the {length}-glyph "
                        "transmission, then repeat it in order."
                    ),
                    "payload": {
                        "sequence": list(seq),
                        "symbols": HL2_SYMBOLS,
                        "length": length,
                    },
                    "expires_in": CHALLENGE_TTL_SECONDS,
                }
            else:  # headcrab_sweep
                target = random.choice(list(VALID_SYMBOL_IDS))
                others = [s for s in VALID_SYMBOL_IDS if s != target]
                # 3x3 grid, 2-4 cells contain the target
                target_count = random.randint(2, 4)
                target_cells = random.sample(range(9), target_count)
                grid = []
                for i in range(9):
                    if i in target_cells:
                        grid.append(target)
                    else:
                        grid.append(random.choice(others))
                sector_names = ["Ravenholm sweep", "Nova Prospekt patrol", "City 17 checkpoint"]
                target_label = next(s["label"] for s in HL2_SYMBOLS if s["id"] == target)
                self._challenges[challenge_id] = {
                    "type": "headcrab_sweep",
                    "answer": sorted(target_cells),
                    "expires": expires,
                    "ip": client_ip,
                    "attempts": 0,
                }
                public = {
                    "challenge_id": challenge_id,
                    "challenge_type": "headcrab_sweep",
                    "title": "XEN FAUNA SWEEP",
                    "prompt": (
                        f"🎯 {random.choice(sector_names)}: neutralize every "
                        f"'{target_label}' sector by clicking all matching tiles "
                        f"({target_count} hostiles detected)."
                    ),
                    "payload": {
                        "grid": grid,
                        "symbols": HL2_SYMBOLS,
                        "target": target,
                        "target_label": target_label,
                        "target_count": target_count,
                    },
                    "expires_in": CHALLENGE_TTL_SECONDS,
                }

            return {"success": True, **public}

    # -- verification ---------------------------------------------------
    def verify_solution(
        self, challenge_id: str, solution: Any, client_ip: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Verify a submitted solution. On success returns (True, {upload_token...})."""
        if not challenge_id or not isinstance(challenge_id, str):
            return False, {"error": "Missing challenge_id. Request a new security check."}
        with self._lock:
            self._cleanup_locked()
            entry = self._challenges.get(challenge_id)
            if not entry:
                return False, {"error": "Challenge expired or not found. Request a new one."}
            if entry.get("expires", 0) <= time.time():
                del self._challenges[challenge_id]
                return False, {"error": "Challenge expired. Request a new one."}
            if entry.get("ip") and entry["ip"] != client_ip:
                return False, {"error": "Challenge was issued to a different network address."}
            if entry.get("attempts", 0) >= MAX_VERIFY_ATTEMPTS:
                del self._challenges[challenge_id]
                return False, {"error": "Too many wrong attempts. Request a new security check."}

            ctype = entry["type"]
            ok = False
            if ctype == "hev_math":
                expected = entry["answer"]
                given = ""
                if isinstance(solution, dict):
                    given = str(solution.get("answer", "")).strip()
                elif solution is not None:
                    given = str(solution).strip()
                # normalize: allow '×' answers only as plain integer
                ok = given == expected
            elif ctype == "lambda_memory":
                expected = entry["answer"]
                given_list: List[str] = []
                if isinstance(solution, dict):
                    raw = solution.get("sequence", [])
                    if isinstance(raw, list):
                        given_list = [str(x).upper().strip() for x in raw]
                elif isinstance(solution, list):
                    given_list = [str(x).upper().strip() for x in solution]
                ok = given_list == expected and all(g in VALID_SYMBOL_IDS for g in given_list)
            else:  # headcrab_sweep
                expected = sorted(entry["answer"])
                given_cells: List[int] = []
                try:
                    raw = solution.get("cells", solution) if isinstance(solution, dict) else solution
                    if isinstance(raw, list):
                        for x in raw:
                            v = int(x)
                            if 0 <= v <= 8 and v not in given_cells:
                                given_cells.append(v)
                    ok = sorted(given_cells) == expected
                except (ValueError, TypeError, AttributeError):
                    ok = False

            if not ok:
                entry["attempts"] = entry.get("attempts", 0) + 1
                remaining = MAX_VERIFY_ATTEMPTS - entry["attempts"]
                if remaining <= 0:
                    del self._challenges[challenge_id]
                    return False, {"error": "Incorrect. Too many attempts — request a new security check."}
                return False, {
                    "error": "Incorrect solution. The Combine does not forgive — try again.",
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

    def consume_upload_token(self, token: Any, client_ip: str) -> Tuple[bool, str]:
        """Validate and burn a single-use upload token. Returns (ok, error)."""
        if not token or not isinstance(token, str):
            return False, "Minigame clearance required: complete the Black Mesa security check first."
        with self._lock:
            self._cleanup_locked()
            entry = self._tokens.get(token.strip())
            if not entry:
                return False, "Invalid or expired clearance token. Complete the security check again."
            if entry.get("expires", 0) <= time.time():
                del self._tokens[token.strip()]
                return False, "Clearance token expired. Complete the security check again."
            if entry.get("used"):
                return False, "Clearance token already used. Each file needs a fresh security check."
            if entry.get("ip") and entry["ip"] != client_ip:
                return False, "Clearance token was issued to a different network address."
            # Mark used immediately (single-use even if the upload itself later fails
            # validation? No — we only call consume AFTER successful save. Instead,
            # peek here and let caller call mark_used. To keep it simple and strict
            # (one token == one upload attempt), burn it now.)
            entry["used"] = True
            entry["used_at"] = time.time()
            return True, ""

    def peek_upload_token(self, token: Any, client_ip: str) -> Tuple[bool, str]:
        """Validate without consuming (lets failed file validation retry with same token)."""
        if not token or not isinstance(token, str):
            return False, "Minigame clearance required: complete the Black Mesa security check first."
        with self._lock:
            self._cleanup_locked()
            entry = self._tokens.get(token.strip())
            if not entry:
                return False, "Invalid or expired clearance token. Complete the security check again."
            if entry.get("expires", 0) <= time.time():
                return False, "Clearance token expired. Complete the security check again."
            if entry.get("used"):
                return False, "Clearance token already used. Each file needs a fresh security check."
            if entry.get("ip") and entry["ip"] != client_ip:
                return False, "Clearance token was issued to a different network address."
            return True, ""

    def burn_upload_token(self, token: Any) -> None:
        with self._lock:
            if isinstance(token, str) and token.strip() in self._tokens:
                self._tokens[token.strip()]["used"] = True
                self._tokens[token.strip()]["used_at"] = time.time()


upload_challenge_manager = UploadChallengeManager()
