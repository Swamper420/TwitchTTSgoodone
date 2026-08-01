import random
import re
import socket
import threading
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger("TwitchListener")

class TwitchListener:
    """Anonymous Twitch IRC socket listener for chat PRIVMSG events."""
    
    IRC_HOST = "irc.chat.twitch.tv"
    IRC_PORT = 6667
    
    def __init__(self, on_message: Callable[[str, str], None]):
        self.on_message = on_message
        self.channel: str = ""
        self.running: bool = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
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
            self._disconnect_socket()
        logger.info("TwitchListener stopped.")
        
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
                nick = f"justinfan{random.randint(10000, 99999)}"
                logger.info(f"Connecting to Twitch IRC ({self.IRC_HOST}:{self.IRC_PORT}) as {nick} for channel #{self.channel}...")
                
                self.sock = socket.create_connection((self.IRC_HOST, self.IRC_PORT), timeout=10)
                self.sock.send(f"PASS SCHMOOPIIE\r\n".encode("utf-8"))
                self.sock.send(f"NICK {nick}\r\n".encode("utf-8"))
                self.sock.send(f"JOIN #{self.channel}\r\n".encode("utf-8"))
                
                logger.info(f"Successfully joined Twitch chat: #{self.channel}")
                
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
