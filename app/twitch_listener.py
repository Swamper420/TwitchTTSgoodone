import logging
import queue
import random
import re
import socket
import ssl
import threading
import time
from typing import Callable, Optional, Dict, Any, List

from app.auth import twitch_token_validator, clean_oauth_token

logger = logging.getLogger("TwitchListener")


def parse_irc_line(line: str) -> Dict[str, Any]:
    """
    Parses a raw Twitch IRC line, supporting IRCv3 tags (@tag=val;...),
    prefix (:nick!user@host or :server), command, target, and trailing message.
    """
    raw = line.strip()
    result: Dict[str, Any] = {
        "tags": {},
        "prefix": "",
        "nick": "",
        "command": "",
        "target": "",
        "params": [],
        "message": "",
        "raw": raw
    }

    if not raw:
        return result

    idx = 0
    length = len(raw)

    # 1. Parse Tags (@key=value;key=value)
    if raw.startswith("@"):
        space_idx = raw.find(" ")
        if space_idx != -1:
            tags_str = raw[1:space_idx]
            idx = space_idx + 1
            for item in tags_str.split(";"):
                if "=" in item:
                    k, v = item.split("=", 1)
                    # Unescape IRC tag values
                    v_unescaped = (v.replace(r"\:", ";")
                                  .replace(r"\s", " ")
                                  .replace(r"\\", "\\")
                                  .replace(r"\r", "\r")
                                  .replace(r"\n", "\n"))
                    result["tags"][k] = v_unescaped
                elif item:
                    result["tags"][item] = True
        else:
            return result

    # Skip spaces
    while idx < length and raw[idx] == " ":
        idx += 1

    # 2. Parse Prefix (:prefix)
    if idx < length and raw[idx] == ":":
        space_idx = raw.find(" ", idx)
        if space_idx != -1:
            result["prefix"] = raw[idx + 1:space_idx]
            idx = space_idx + 1
            if "!" in result["prefix"]:
                result["nick"] = result["prefix"].split("!", 1)[0]
            else:
                result["nick"] = result["prefix"]
        else:
            return result

    # Skip spaces
    while idx < length and raw[idx] == " ":
        idx += 1

    # 3. Parse Command and Params
    rest = raw[idx:]
    if not rest:
        return result

    if " :" in rest:
        args_str, trailing = rest.split(" :", 1)
        result["message"] = trailing
    else:
        args_str = rest
        trailing = None

    parts = [p for p in args_str.split(" ") if p]
    if parts:
        result["command"] = parts[0].upper()
        if len(parts) > 1:
            result["target"] = parts[1]
            result["params"] = parts[1:]

    return result


class TwitchListener:
    """Twitch IRC socket listener and sender for chat PRIVMSG events."""

    IRC_HOST = "irc.chat.twitch.tv"
    IRC_PORT_SSL = 6697
    IRC_PORT_PLAIN = 6667

    def __init__(self, on_message: Callable[[str, str], None], bot_username: str = "", oauth_token: str = ""):
        self.on_message = on_message
        self.on_message = on_message
        self.channel: str = ""
        self.channels: List[str] = []
        self.bot_username: str = bot_username.strip()
        self.oauth_token: str = oauth_token.strip()
        self.running: bool = False
        self.is_authenticated: bool = False
        self.auth_info: Dict[str, Any] = {}
        self.sock: Optional[socket.socket] = None
        self.recv_thread: Optional[threading.Thread] = None
        self.send_thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()
        self._send_queue: queue.Queue = queue.Queue()
        self._force_reconnect: bool = False
        self._last_send_time: float = 0.0
        self._rate_limit_delay: float = 1.2  # Seconds between sent PRIVMSGs

        if self.oauth_token:
            self._validate_and_update_token(self.bot_username, self.oauth_token)

    def _validate_and_update_token(self, bot_username: str, oauth_token: str) -> Dict[str, Any]:
        info = twitch_token_validator.validate_token(oauth_token)
        with self._lock:
            self.auth_info = info
            explicit_user = bot_username.strip() if bot_username else ""
            if explicit_user:
                self.bot_username = explicit_user
                logger.info(f"Using configured Twitch bot username '@{self.bot_username}' from environment/settings.")
            elif info.get("valid") and info.get("login"):
                self.bot_username = info["login"]
                logger.info(f"Auto-detected Twitch bot username '@{self.bot_username}' from OAuth token.")
            else:
                self.bot_username = ""

            if not info.get("valid"):
                err_msg = info.get("error", "Unknown validation error")
                logger.warning(f"Twitch OAuth token API validation note ({err_msg}). IRC auth will attempt directly as '@{self.bot_username}'.")
        return info

    def set_credentials(self, bot_username: str, oauth_token: str):
        """Set or update bot authentication credentials."""
        with self._lock:
            new_bot = bot_username.strip()
            new_oauth = oauth_token.strip()
            if self.bot_username != new_bot or self.oauth_token != new_oauth:
                self.bot_username = new_bot
                self.oauth_token = new_oauth
                self._force_reconnect = True
                if self.oauth_token:
                    self._validate_and_update_token(self.bot_username, self.oauth_token)
                else:
                    self.auth_info = {}

                logger.info(f"Updated Twitch bot credentials (bot_username='{self.bot_username}')")
                if self.running:
                    self._disconnect_socket()

    def set_channel(self, channel: str):
        """Set or switch Twitch channel(s). Supports up to 2 comma-separated channels."""
        raw_list = [c.strip().lstrip('#').lower() for c in channel.replace(';', ',').split(',') if c.strip()]
        unique_channels = []
        for ch in raw_list:
            if ch and ch not in unique_channels:
                unique_channels.append(ch)
        new_channels = unique_channels[:2]

        with self._lock:
            if self.channels != new_channels:
                self.channels = new_channels
                self.channel = new_channels[0] if new_channels else ""
                self._force_reconnect = True
                ch_str = ", #".join(self.channels)
                logger.info(f"Twitch channels set to: #{ch_str}")
                if self.running:
                    self._disconnect_socket()

    def get_auth_info(self) -> Dict[str, Any]:
        """Return current Twitch token validation metadata."""
        with self._lock:
            return dict(self.auth_info)

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive status of Twitch listener."""
        with self._lock:
            return {
                "running": self.running,
                "connected": bool(self.sock),
                "is_authenticated": self.is_authenticated,
                "bot_username": self.bot_username,
                "channel": self.channel,
                "channels": list(self.channels),
                "queue_size": self._send_queue.qsize(),
                "auth_info": dict(self.auth_info)
            }

    def start(self, channel: Optional[str] = None):
        """Start Twitch chat listener in background thread."""
        if channel:
            self.set_channel(channel)

        with self._lock:
            if self.running:
                return
            self.running = True

        self.recv_thread = threading.Thread(target=self._run_loop, daemon=True, name="TwitchRecvLoop")
        self.recv_thread.start()

        self.send_thread = threading.Thread(target=self._send_worker, daemon=True, name="TwitchSendLoop")
        self.send_thread.start()

        logger.info("TwitchListener background threads started.")

    def stop(self):
        """Stop Twitch listener."""
        with self._lock:
            self.running = False
            self.is_authenticated = False
            self._disconnect_socket()
        logger.info("TwitchListener stopped.")

    def reconnect(self):
        """Trigger an explicit socket reconnect."""
        with self._lock:
            self._force_reconnect = True
            self._disconnect_socket()
        logger.info("TwitchListener reconnect requested.")

    def send_chat(self, message: str, channel: Optional[str] = None) -> bool:
        """
        Queue a text PRIVMSG message to send to a target Twitch channel.
        Defaults to primary channel if unspecified.
        """
        if not message or not message.strip():
            return False

        with self._lock:
            curr_channels = list(self.channels)
            primary_channel = self.channel
            authenticated = self.is_authenticated
            is_running = self.running

        target_ch = channel.strip().lstrip('#').lower() if channel else primary_channel
        if not target_ch and curr_channels:
            target_ch = curr_channels[0]

        if not target_ch:
            logger.warning("Cannot send Twitch chat message: No channel configured.")
            return False

        if not is_running:
            logger.warning("Cannot send Twitch chat message: TwitchListener is not running.")
            return False

        if not authenticated:
            logger.warning("Cannot send Twitch chat message: Bot is in anonymous reader mode (not authenticated).")
            return False

        clean_msg = message.replace("\r", " ").replace("\n", " ").strip()
        if not clean_msg:
            return False

        # Truncate long PRIVMSGs to fit within IRC 500-char limit
        if len(clean_msg) > 480:
            clean_msg = clean_msg[:477] + "..."

        self._send_queue.put((target_ch, clean_msg))
        logger.info(f"Queued Twitch chat message for #{target_ch}: '{clean_msg[:30]}...'")
        return True

    def _send_worker(self):
        """Background worker thread processing queued outbound PRIVMSG chat messages with rate limiting."""
        while self.running:
            try:
                try:
                    target_channel, clean_msg = self._send_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # Wait for rate limit if needed
                now = time.time()
                elapsed = now - self._last_send_time
                if elapsed < self._rate_limit_delay:
                    time.sleep(self._rate_limit_delay - elapsed)

                with self._lock:
                    sock_ref = self.sock
                    authenticated = self.is_authenticated

                if sock_ref and authenticated:
                    irc_cmd = f"PRIVMSG #{target_channel} :{clean_msg}\r\n"
                    try:
                        sock_ref.sendall(irc_cmd.encode("utf-8"))
                        self._last_send_time = time.time()
                        logger.info(f"Twitch Bot -> #{target_channel}: {clean_msg}")
                    except Exception as e:
                        logger.error(f"Failed to send Twitch chat message via socket: {e}")
                else:
                    logger.warning(f"Dropped queued message for #{target_channel} (socket disconnected or not authenticated).")

                self._send_queue.task_done()

            except Exception as e:
                logger.error(f"Error in Twitch send worker: {e}")
                time.sleep(0.5)

    def _disconnect_socket(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _run_loop(self):
        fallback_anon = False
        last_creds = None

        while self.running:
            if not self.channels and not self.channel:
                time.sleep(1.0)
                continue

            try:
                with self._lock:
                    bot_user = self.bot_username.strip()
                    raw_token = self.oauth_token.strip()
                    forced_recon = self._force_reconnect
                    self._force_reconnect = False

                clean_tok = clean_oauth_token(raw_token)
                current_creds = (bot_user, clean_tok)

                if current_creds != last_creds or forced_recon:
                    fallback_anon = False
                    last_creds = current_creds

                use_auth = bool(bot_user and clean_tok) and not fallback_anon
                ch_display = ", #".join(self.channels) if self.channels else (f"#{self.channel}" if self.channel else "")

                if use_auth:
                    nick = bot_user.lower()
                    pass_str = f"oauth:{clean_tok}"
                    self.is_authenticated = False
                    logger.info(f"Connecting to Twitch IRC ({self.IRC_HOST}:{self.IRC_PORT_SSL} SSL) as BOT '{nick}' for channels: #{ch_display}...")
                else:
                    nick = f"justinfan{random.randint(10000, 99999)}"
                    pass_str = "SCHMOOPIIE"
                    self.is_authenticated = False
                    if bot_user and clean_tok and fallback_anon:
                        logger.warning(f"Connecting to Twitch IRC as ANONYMOUS reader {nick} (Auth failed for BOT '{bot_user}'). Chat TTS active, bot replies disabled.")
                    else:
                        logger.info(f"Connecting to Twitch IRC as ANONYMOUS reader {nick} for channels: #{ch_display}...")

                try:
                    raw_sock = socket.create_connection((self.IRC_HOST, self.IRC_PORT_SSL), timeout=10)
                    ctx = ssl.create_default_context()
                    self.sock = ctx.wrap_socket(raw_sock, server_hostname=self.IRC_HOST)
                except Exception as ssl_err:
                    logger.warning(f"SSL IRC connection failed ({ssl_err}). Falling back to port {self.IRC_PORT_PLAIN}...")
                    self.sock = socket.create_connection((self.IRC_HOST, self.IRC_PORT_PLAIN), timeout=10)

                # Send Twitch IRC capability requests and credentials
                self.sock.sendall(b"CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands\r\n")
                self.sock.sendall(f"PASS {pass_str}\r\n".encode("utf-8"))
                self.sock.sendall(f"NICK {nick}\r\n".encode("utf-8"))
                
                target_channels = self.channels if self.channels else ([self.channel] if self.channel else [])
                for ch in target_channels:
                    self.sock.sendall(f"JOIN #{ch}\r\n".encode("utf-8"))

                buffer = ""
                self.sock.settimeout(2.0)

                while self.running and self.sock:
                    try:
                        data = self.sock.recv(4096).decode("utf-8", errors="ignore")
                        if not data:
                            logger.warning("Twitch IRC socket closed by server.")
                            break

                        buffer += data
                        lines = buffer.split("\r\n")
                        buffer = lines.pop()

                        auth_failed_in_batch = False
                        for line in lines:
                            res = self._handle_irc_line(line, expected_auth=use_auth)
                            if res == "AUTH_FAILED":
                                logger.error(f"Twitch IRC authentication failed for bot '{bot_user}'. Falling back to anonymous reader mode.")
                                fallback_anon = True
                                auth_failed_in_batch = True
                                break

                        if auth_failed_in_batch:
                            break

                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            logger.error(f"Error receiving Twitch chat data: {e}")
                        break

            except Exception as e:
                if self.running:
                    logger.warning(f"Twitch connection error: {e}. Reconnecting in 3s...")
            finally:
                self._disconnect_socket()
                if self.running:
                    time.sleep(3.0)

    def _handle_irc_line(self, line: str, expected_auth: bool = False) -> Optional[str]:
        if not line or not line.strip():
            return None

        parsed = parse_irc_line(line)
        cmd = parsed["command"]
        msg = parsed["message"]
        nick = parsed["nick"]
        line_lower = line.lower()

        # Handle PING / PONG heartbeat
        if cmd == "PING" or line.startswith("PING"):
            pong_resp = f"PONG {msg or 'tmi.twitch.tv'}\r\n"
            if self.sock:
                try:
                    self.sock.sendall(pong_resp.encode("utf-8"))
                except Exception:
                    pass
            return None

        # Handle Twitch NOTICE messages (authentication failure checks)
        if cmd == "NOTICE" or "NOTICE" in line:
            logger.warning(f"Twitch IRC Server NOTICE: {line}")
            auth_err_patterns = [
                "login authentication failed",
                "improperly formatted auth",
                "login unsuccessful",
                "error logging in",
                "invalid nick"
            ]
            if any(pattern in line_lower for pattern in auth_err_patterns):
                with self._lock:
                    self.is_authenticated = False
                return "AUTH_FAILED"

        # Welcome message (001) confirms successful authentication / connection
        if cmd == "001" or " 001 " in line:
            ch_display = ", #".join(self.channels) if self.channels else f"#{self.channel}"
            if expected_auth:
                with self._lock:
                    self.is_authenticated = True
                logger.info(f"Twitch IRC Authentication SUCCESSFUL for BOT '{self.bot_username}'. Joined chat: #{ch_display}")
            else:
                with self._lock:
                    self.is_authenticated = False
                logger.info(f"Twitch IRC successfully joined chat anonymously as reader: #{ch_display}")

        # PRIVMSG chat messages
        if cmd == "PRIVMSG":
            # Prefer display-name tag if present, else fallback to IRC nick
            user_display = parsed["tags"].get("display-name") or nick or "Chatter"
            raw_target = parsed["target"].strip().lstrip('#').lower() if parsed["target"] else ""
            target_chan = raw_target or self.channel
            chat_text = msg
            logger.info(f"Twitch Chat [#{target_chan}] {user_display}: {chat_text}")
            try:
                try:
                    self.on_message(user_display, chat_text, target_chan)
                except TypeError:
                    self.on_message(user_display, chat_text)
            except Exception as e:
                logger.error(f"Error processing chat message from {user_display}: {e}")

        return None
