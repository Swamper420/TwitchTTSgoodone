import random
import re
import socket
import threading
import time
import logging
from typing import Callable, Optional

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
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        
    def set_credentials(self, bot_username: str, oauth_token: str):
        """Set or update bot authentication credentials."""
        with self._lock:
            new_bot = bot_username.strip()
            new_oauth = oauth_token.strip()
            if self.bot_username != new_bot or self.oauth_token != new_oauth:
                self.bot_username = new_bot
                self.oauth_token = new_oauth
                logger.info(f"Updated Twitch bot credentials (bot_username='{self.bot_username}')")
                if self.running:
                    self._disconnect_socket()

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
        while self.running:
            if not self.channel:
                time.sleep(1.0)
                continue
                
            try:
                with self._lock:
                    bot_user = self.bot_username
                    oauth_tok = self.oauth_token

                if bot_user and oauth_tok:
                    nick = bot_user.lower()
                    pass_str = oauth_tok if oauth_tok.startswith("oauth:") else f"oauth:{oauth_tok}"
                    self.is_authenticated = True
                    logger.info(f"Connecting to Twitch IRC ({self.IRC_HOST}:{self.IRC_PORT}) as BOT '{nick}' for channel #{self.channel}...")
                else:
                    nick = f"justinfan{random.randint(10000, 99999)}"
                    pass_str = "SCHMOOPIIE"
                    self.is_authenticated = False
                    logger.info(f"Connecting to Twitch IRC ({self.IRC_HOST}:{self.IRC_PORT}) as ANONYMOUS {nick} for channel #{self.channel}...")
                
                self.sock = socket.create_connection((self.IRC_HOST, self.IRC_PORT), timeout=10)
                self.sock.send(f"PASS {pass_str}\r\n".encode("utf-8"))
                self.sock.send(f"NICK {nick}\r\n".encode("utf-8"))
                self.sock.send(f"JOIN #{self.channel}\r\n".encode("utf-8"))
                
                logger.info(f"Successfully joined Twitch chat: #{self.channel} (Authenticated: {self.is_authenticated})")
                
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
                        
                        for line in lines:
                            self._handle_irc_line(line)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            logger.error(f"Error receiving Twitch chat data: {e}")
                        break
                        
            except Exception as e:
                if self.running:
                    logger.warning(f"Twitch connection error: {e}. Reconnecting in 5s...")
                    time.sleep(5)
            finally:
                self._disconnect_socket()
                
    def _handle_irc_line(self, line: str):
        line = line.strip()
        if not line:
            return
            
        # PING / PONG heartbeat
        if line.startswith("PING"):
            pong_resp = line.replace("PING", "PONG")
            if self.sock:
                try:
                    with self._send_lock:
                        self.sock.send(f"{pong_resp}\r\n".encode("utf-8"))
                except Exception:
                    pass
            return
            
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
