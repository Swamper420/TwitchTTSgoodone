import random
import re
import socket
import threading
import time
import logging
from typing import Callable, Optional, Dict, Any

from app.auth import twitch_token_validator

logger = logging.getLogger("TwitchListener")

class TwitchListener:
    """Twitch IRC socket listener and sender for chat PRIVMSG events."""
    
    IRC_HOST = "irc.chat.twitch.tv"
    IRC_PORT = 6667
    
    def __init__(self, on_message: Callable[[str, str], None], bot_username: str = "", oauth_token: str = ""):
        self.on_message = on_message
        self.channel: str = ""
        self.bot_username: str = bot_username.strip()
        self.oauth_token: str = oauth_token.strip()
        self.running: bool = False
        self.is_authenticated: bool = False
        self.auth_info: Dict[str, Any] = {}
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        
        if self.oauth_token:
            self._validate_and_update_token(self.bot_username, self.oauth_token)

    def _validate_and_update_token(self, bot_username: str, oauth_token: str) -> Dict[str, Any]:
        info = twitch_token_validator.validate_token(oauth_token)
        self.auth_info = info
        if info.get("valid"):
            if not bot_username and info.get("login"):
                self.bot_username = info["login"]
                logger.info(f"Auto-detected Twitch bot username '@{self.bot_username}' from OAuth token metadata.")
        return info
        
    def set_credentials(self, bot_username: str, oauth_token: str):
        """Set or update bot authentication credentials."""
        with self._lock:
            new_bot = bot_username.strip()
            new_oauth = oauth_token.strip()
            if self.bot_username != new_bot or self.oauth_token != new_oauth:
                self.bot_username = new_bot
                self.oauth_token = new_oauth
                if self.oauth_token:
                    info = self._validate_and_update_token(self.bot_username, self.oauth_token)
                    if info.get("valid") and not self.bot_username:
                        self.bot_username = info["login"]
                else:
                    self.auth_info = {}
                    
                logger.info(f"Updated Twitch bot credentials (bot_username='{self.bot_username}')")
                if self.running:
                    self._disconnect_socket()

    def get_auth_info(self) -> Dict[str, Any]:
        """Return current Twitch token validation metadata."""
        with self._lock:
            return dict(self.auth_info)


    def set_channel(self, channel: str):
        """Set or switch Twitch channel."""
        channel_clean = channel.strip().lstrip('#').lower()
        with self._lock:
            if self.channel != channel_clean:
                self.channel = channel_clean
                logger.info(f"Twitch channel set to: #{self.channel}")
                if self.running:
                    # Reconnect to join new channel
                    self._disconnect_socket()
                    
    def start(self, channel: Optional[str] = None):
        """Start Twitch chat listener in background thread."""
        if channel:
            self.set_channel(channel)
            
        with self._lock:
            if self.running:
                return
            self.running = True
            
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("TwitchListener background thread started.")
        
    def stop(self):
        """Stop Twitch listener."""
        with self._lock:
            self.running = False
            self.is_authenticated = False
            self._disconnect_socket()
        logger.info("TwitchListener stopped.")
        
    def send_chat(self, message: str) -> bool:
        """Send a text PRIVMSG message to the current Twitch channel."""
        if not message or not self.channel:
            return False
            
        with self._send_lock:
            if not self.sock or not self.running:
                logger.warning("Cannot send Twitch chat message: socket not connected.")
                return False
            
            # Clean newlines from chat message
            clean_msg = message.replace("\r", " ").replace("\n", " ").strip()
            if not clean_msg:
                return False
                
            irc_cmd = f"PRIVMSG #{self.channel} :{clean_msg}\r\n"
            try:
                self.sock.send(irc_cmd.encode("utf-8"))
                logger.info(f"Twitch Bot -> #{self.channel}: {clean_msg}")
                return True
            except Exception as e:
                logger.error(f"Failed to send Twitch chat message: {e}")
                return False

    def _disconnect_socket(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _run_loop(self):
        fallback_anon = False
        last_auth_attempt = None

        while self.running:
            if not self.channel:
                time.sleep(1.0)
                continue

            try:
                with self._lock:
                    bot_user = self.bot_username
                    oauth_tok = self.oauth_token

                current_creds = (bot_user, oauth_tok)
                if current_creds != last_auth_attempt:
                    fallback_anon = False
                    last_auth_attempt = current_creds

                use_auth = bool(bot_user and oauth_tok) and not fallback_anon

                if use_auth:
                    nick = bot_user.lower()
                    pass_str = oauth_tok if oauth_tok.startswith("oauth:") else f"oauth:{oauth_tok}"
                    self.is_authenticated = False
                    logger.info(f"Connecting to Twitch IRC ({self.IRC_HOST}:{self.IRC_PORT}) as BOT '{nick}' for channel #{self.channel}...")
                else:
                    nick = f"justinfan{random.randint(10000, 99999)}"
                    pass_str = "SCHMOOPIIE"
                    self.is_authenticated = False
                    if bot_user and oauth_tok and fallback_anon:
                        logger.warning(f"Connecting to Twitch IRC as ANONYMOUS reader {nick} (Auth failed for BOT '{bot_user}'). Chat TTS enabled, bot chat replies disabled.")
                    else:
                        logger.info(f"Connecting to Twitch IRC as ANONYMOUS reader {nick} for channel #{self.channel}...")

                self.sock = socket.create_connection((self.IRC_HOST, self.IRC_PORT), timeout=10)
                self.sock.send(f"PASS {pass_str}\r\n".encode("utf-8"))
                self.sock.send(f"NICK {nick}\r\n".encode("utf-8"))
                self.sock.send(f"JOIN #{self.channel}\r\n".encode("utf-8"))

                buffer = ""
                self.sock.settimeout(2.0)

                while self.running and self.sock:
                    try:
                        data = self.sock.recv(4096).decode("utf-8", errors="ignore")
                        if not data:
                            logger.warning("Twitch socket closed by server.")
                            break
                        buffer += data
                        lines = buffer.split("\r\n")
                        buffer = lines.pop()

                        auth_failed_in_batch = False
                        for line in lines:
                            res = self._handle_irc_line(line, expected_auth=use_auth)
                            if res == "AUTH_FAILED":
                                logger.error(f"Twitch IRC authentication failed for bot '{bot_user}'. Switching to anonymous reader mode.")
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
                    logger.warning(f"Twitch connection error: {e}. Reconnecting in 5s...")
            finally:
                self._disconnect_socket()
                if self.running:
                    time.sleep(3.0)

    def _handle_irc_line(self, line: str, expected_auth: bool = False) -> Optional[str]:
        line = line.strip()
        if not line:
            return None

        # PING / PONG heartbeat
        if line.startswith("PING"):
            pong_resp = line.replace("PING", "PONG")
            if self.sock:
                try:
                    with self._send_lock:
                        self.sock.send(f"{pong_resp}\r\n".encode("utf-8"))
                except Exception:
                    pass
            return None

        # Twitch IRC NOTICE messages (e.g. authentication errors)
        if "NOTICE" in line:
            logger.warning(f"Twitch IRC Server NOTICE: {line}")
            if any(err_msg in line for err_msg in ["Login unsuccessful", "Login authentication failed", "Improperly formatted auth"]):
                self.is_authenticated = False
                return "AUTH_FAILED"

        # Welcome message (001) confirms successful connection
        if " 001 " in line:
            if expected_auth:
                self.is_authenticated = True
                logger.info(f"Twitch IRC Authentication SUCCESSFUL for BOT '{self.bot_username}'. Joined chat: #{self.channel}")
            else:
                self.is_authenticated = False
                logger.info(f"Twitch IRC Successfully joined chat anonymously as reader: #{self.channel}")

        # Match PRIVMSG line: :username!username@username.tmi.twitch.tv PRIVMSG #channel :message
        match = re.match(r'^:([^!]+)![^@]+@[^\s]+\s+PRIVMSG\s+#[^\s]+\s+:(.*)$', line)
        if match:
            username = match.group(1)
            message = match.group(2)
            logger.info(f"Twitch Chat [{self.channel}] {username}: {message}")
            try:
                self.on_message(username, message)
            except Exception as e:
                logger.error(f"Error processing chat message from {username}: {e}")

        return None
