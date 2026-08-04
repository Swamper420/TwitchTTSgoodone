import datetime
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("Auth")

TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"


def clean_oauth_token(token: str) -> str:
    """Clean and strip prefixes (oauth:, bearer:), quotes, and whitespace from token string."""
    if not token:
        return ""
    tok = token.strip().strip('"').strip("'")
    import re
    # Remove repeated leading oauth: or bearer: prefixes case-insensitively
    while True:
        m = re.match(r'^(oauth:|bearer:)\s*', tok, flags=re.IGNORECASE)
        if m:
            tok = tok[m.end():].strip().strip('"').strip("'")
        else:
            break
    return tok


def mask_token(token: str, keep_chars: int = 4) -> str:
    """Mask a sensitive token string (e.g. oauth:xxxxxxxx -> oauth:••••••••abcd)."""
    if not token:
        return ""
    has_oauth_prefix = token.strip().lower().startswith("oauth:")
    raw_tok = clean_oauth_token(token)
    prefix = "oauth:" if has_oauth_prefix else ""

    if len(raw_tok) <= keep_chars:
        return prefix + "•" * len(raw_tok)

    masked_part = "•" * max(4, len(raw_tok) - keep_chars)
    suffix = raw_tok[-keep_chars:]
    return f"{prefix}{masked_part}{suffix}"


HASH_PREFIX = "pbkdf2_sha256$"
PBKDF2_ITERATIONS = 260000


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256 with a random salt."""
    if not password:
        return ""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return f"{HASH_PREFIX}{PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash or plaintext (legacy migration)."""
    if not password or not stored:
        return False

    if stored.startswith(HASH_PREFIX):
        try:
            remainder = stored[len(HASH_PREFIX):]
            iterations_str, salt_hex, hash_hex = remainder.split('$', 2)
            dk = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations_str)
            )
            return secrets.compare_digest(dk.hex(), hash_hex)
        except (ValueError, IndexError):
            return False
    else:
        # Legacy plaintext comparison (timing-safe)
        return secrets.compare_digest(password, stored)


class TwitchTokenValidator:
    """
    Validates Twitch OAuth 2.0 access tokens directly against the official
    Twitch ID validation API (https://id.twitch.tv/oauth2/validate).
    """

    @staticmethod
    def validate_token(oauth_token: str) -> Dict[str, Any]:
        """
        Validates a Twitch OAuth token.
        Returns a dictionary containing:
        - valid (bool)
        - login (str) - Twitch username associated with token
        - user_id (str) - Twitch user ID
        - client_id (str) - Client ID of the registering app
        - scopes (list[str]) - Authorized OAuth scopes (e.g., ['chat:read', 'chat:edit'])
        - expires_in (int) - Remaining validity in seconds
        - expires_at_iso (str) - Calculated ISO timestamp of expiration
        - error (str or None) - Error description if invalid
        """
        raw_token = clean_oauth_token(oauth_token)
        if not raw_token:
            return {
                "valid": False,
                "login": "",
                "user_id": "",
                "client_id": "",
                "scopes": [],
                "expires_in": 0,
                "expires_at_iso": None,
                "error": "No OAuth token provided",
            }

        token_for_header = raw_token

        req = urllib.request.Request(TWITCH_VALIDATE_URL)
        # Twitch validate endpoint accepts "Authorization: OAuth <token>" or "Authorization: Bearer <token>"
        req.add_header("Authorization", f"OAuth {token_for_header}")
        req.add_header("User-Agent", "TwitchTTSBot/2.0")

        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    expires_in = data.get("expires_in", 0)
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    expires_at = now_utc + datetime.timedelta(seconds=expires_in)

                    login = data.get("login", "")
                    scopes = data.get("scopes", [])
                    client_id = data.get("client_id", "")
                    user_id = data.get("user_id", "")

                    logger.info(
                        f"Twitch OAuth Token validated successfully for user '@{login}' "
                        f"(Client ID: {client_id[:6]}..., Scopes: {scopes}, Expires in {expires_in}s)"
                    )

                    return {
                        "valid": True,
                        "login": login,
                        "user_id": user_id,
                        "client_id": client_id,
                        "scopes": scopes,
                        "expires_in": expires_in,
                        "expires_at_iso": expires_at.isoformat(),
                        "error": None,
                    }
                else:
                    logger.warning(f"Twitch token validation returned HTTP {resp.status}")
                    return {
                        "valid": False,
                        "login": "",
                        "user_id": "",
                        "client_id": "",
                        "scopes": [],
                        "expires_in": 0,
                        "expires_at_iso": None,
                        "error": f"Twitch API returned HTTP {resp.status}",
                    }
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
                err_json = json.loads(error_body)
                error_msg = err_json.get("message", f"HTTP {e.code} Error")
            except Exception:
                error_msg = f"HTTP {e.code}: {e.reason}"

            logger.warning(f"Twitch OAuth Token Validation failed: {error_msg}")
            return {
                "valid": False,
                "login": "",
                "user_id": "",
                "client_id": "",
                "scopes": [],
                "expires_in": 0,
                "expires_at_iso": None,
                "error": error_msg,
            }
        except Exception as e:
            logger.error(f"Error during Twitch OAuth token validation: {e}")
            return {
                "valid": False,
                "login": "",
                "user_id": "",
                "client_id": "",
                "scopes": [],
                "expires_in": 0,
                "expires_at_iso": None,
                "error": str(e),
            }


class DashboardAuthManager:
    """
    Manages Web Dashboard and Streamer Control Portal security, session tokens,
    role-based authorization (admin vs user), and separate password protection.
    """

    def __init__(self, admin_password: str = "", user_password: str = ""):
        self.admin_password = admin_password.strip()
        self.user_password = user_password.strip()
        self._active_sessions: Dict[str, Dict[str, Any]] = {}  # token -> {"exp": timestamp, "role": "admin"|"user"}
        self._session_ttl_seconds = 86400  # 24 hours

    def update_admin_password(self, password: str):
        """Update admin password and clear sessions if password changed."""
        new_pwd = password.strip()
        if self.admin_password != new_pwd:
            self.admin_password = new_pwd
            self._active_sessions.clear()
            logger.info(
                f"Dashboard admin password updated. (Protection {'ENABLED' if self.admin_password else 'DISABLED'})"
            )

    def update_user_password(self, password: str):
        """Update control portal user password."""
        new_pwd = password.strip()
        if self.user_password != new_pwd:
            self.user_password = new_pwd
            self._active_sessions.clear()
            logger.info(
                f"Control portal user password updated. (Protection {'ENABLED' if self.user_password else 'DISABLED'})"
            )

    def update_passwords(self, admin_password: str = "", user_password: str = ""):
        self.update_admin_password(admin_password)
        self.update_user_password(user_password)

    def is_admin_auth_required(self) -> bool:
        """Returns True if an admin password is configured."""
        return bool(self.admin_password)

    def is_user_auth_required(self) -> bool:
        """Returns True if a user password or admin password is configured for control page."""
        return bool(self.user_password or self.admin_password)

    def is_auth_required(self) -> bool:
        """Returns True if any password protection is configured."""
        return self.is_admin_auth_required() or self.is_user_auth_required()

    def authenticate(self, password: str) -> Tuple[bool, Optional[str], Optional[str], str]:
        """
        Authenticate with password.
        Checks Admin password first (grants 'admin' role).
        Checks User password second (grants 'user' role).
        Returns: (success, session_token, error_message, role)
        """
        pwd = password.strip() if password else ""

        # Check Admin password first
        if self.admin_password and verify_password(pwd, self.admin_password):
            token = secrets.token_hex(24)
            self._active_sessions[token] = {
                "exp": time.time() + self._session_ttl_seconds,
                "role": "admin"
            }
            logger.info("Successful Dashboard Admin Login.")
            return True, token, None, "admin"

        # Check User / Control page password
        if self.user_password and verify_password(pwd, self.user_password):
            token = secrets.token_hex(24)
            self._active_sessions[token] = {
                "exp": time.time() + self._session_ttl_seconds,
                "role": "user"
            }
            logger.info("Successful Streamer Control Portal User Login.")
            return True, token, None, "user"

        # If no password set on server at all, grant admin guest token
        if not self.is_admin_auth_required() and not self.is_user_auth_required():
            token = secrets.token_hex(24)
            self._active_sessions[token] = {
                "exp": time.time() + self._session_ttl_seconds,
                "role": "admin"
            }
            return True, token, None, "admin"

        logger.warning("Failed Login attempt.")
        return False, None, "Invalid password", ""

    def verify_session(self, token: str, required_role: str = "user") -> bool:
        """
        Verify if a session token is valid and active for required role.
        - 'admin' role satisfies both 'admin' and 'user' requirements.
        - 'user' role satisfies 'user' requirement.
        """
        if required_role == "admin" and not self.is_admin_auth_required():
            return True
        if required_role == "user" and not self.is_user_auth_required():
            return True

        if not token:
            return False

        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()

        sess = self._active_sessions.get(clean_token)
        if not sess:
            return False

        exp = sess.get("exp", 0)
        if time.time() > exp:
            del self._active_sessions[clean_token]
            return False

        role = sess.get("role", "user")
        if required_role == "admin" and role != "admin":
            return False

        return True

    def get_session_role(self, token: str) -> Optional[str]:
        if not token:
            return None
        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()
        sess = self._active_sessions.get(clean_token)
        if sess and time.time() <= sess.get("exp", 0):
            return sess.get("role", "user")
        return None

    def revoke_session(self, token: str):
        """Revoke a session token."""
        if not token:
            return
        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()
        if clean_token in self._active_sessions:
            del self._active_sessions[clean_token]

    def cleanup_expired_sessions(self):
        """Remove expired sessions from memory."""
        now = time.time()
        expired = [t for t, sess in self._active_sessions.items() if now > sess.get("exp", 0)]
        for t in expired:
            del self._active_sessions[t]


# Global Auth Manager instances
twitch_token_validator = TwitchTokenValidator()
dashboard_auth_manager = DashboardAuthManager()
