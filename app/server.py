import json
import logging
import os
import queue
import threading
import time
import uuid
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Tuple, List, Optional
import urllib.parse

from app.config import config
from app.text_chunker import process_message_to_chunks, TTSChunk
from app.tts_client import tts_client, TTSClient
from app.twitch_listener import TwitchListener
from app.user_voices import user_voice_manager
from app.auth import dashboard_auth_manager, twitch_token_validator, mask_token

logger = logging.getLogger("Server")

# Global Audio Storage & Queue
# audio_id -> (bytes, mime_type, metadata_dict)
audio_store: Dict[str, Tuple[bytes, str, dict]] = {}
audio_queue: List[dict] = []

# Event subscriptions (SSE)
sse_clients: List[queue.Queue] = []

# Twitch Listener instance
twitch_bot: Optional[TwitchListener] = None

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def broadcast_event(event_type: str, payload: dict):
    """Send SSE event to all connected web clients."""
    msg = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
    to_remove = []
    for q in sse_clients:
        try:
            q.put_nowait(msg)
        except Exception:
            to_remove.append(q)
    for q in to_remove:
        if q in sse_clients:
            sse_clients.remove(q)


def send_bot_helpful_info() -> str:
    """Send helpful info about TTS bot features to chat & SSE UI."""
    info_text = f"🎙️ Twitch TTS Bot Info: Set your default voice with '!myvoice <voice>' (e.g. !myvoice mieto) or reset with '!myvoice reset'. Preset voices: [{config.voice_presets}]. Use [voicename] tags in chat for multi-voice!"
    broadcast_event("chat_message", {"user": "System", "message": info_text, "timestamp": time.time()})
    if config.enable_chat_responses and twitch_bot:
        twitch_bot.send_chat(info_text)
    return info_text


def _periodic_info_loop():
    logger.info("Periodic info background thread running.")
    while True:
        try:
            interval_mins = max(1, config.periodic_info_interval)
            time.sleep(interval_mins * 60)
            if config.enable_periodic_info and twitch_bot and twitch_bot.running and twitch_bot.channel:
                logger.info("Broadcasting periodic helpful info to Twitch chat...")
                send_bot_helpful_info()
        except Exception as e:
            logger.error(f"Error in periodic info loop: {e}")


last_command_broadcast_time = 0.0

def process_incoming_text(user: str, raw_text: str, override_voice: Optional[str] = None, override_model: Optional[str] = None):
    """
    Process incoming chat or test message:
    1. Intercept chat commands (!help, !tts, !botinfo, !voices, !myvoice, !skip, !clear).
    2. Prepend user template to regular text.
    3. Parse into chunks (with per-chunk voice tags if present).
    4. Request local TTS API for each chunk.
    5. Save audio to memory store and notify frontend player via SSE.
    """
    global last_command_broadcast_time

    if raw_text:
        raw_lower = raw_text.strip().lower()

        # Command: !skip / !clear
        if raw_lower in ("!skip", "!next"):
            logger.info(f"Chat command '!skip' received from user '{user}'.")
            broadcast_event("skip_audio", {"user": user, "timestamp": time.time()})
            return

        if raw_lower in ("!clear", "!clearqueue", "!stop"):
            logger.info(f"Chat command '!clear' received from user '{user}'.")
            audio_queue.clear()
            broadcast_event("clear_audio", {"user": user, "timestamp": time.time()})
            return

        # Command: !help, !tts, !botinfo, !info, !about
        if raw_lower in ("!help", "!tts", "!botinfo", "!info", "!about"):
            now = time.time()
            if now - last_command_broadcast_time > 3.0:
                last_command_broadcast_time = now
                send_bot_helpful_info()
            return

        # Command: !voices
        if raw_lower in ("!voices", "!preset", "!presets"):
            now = time.time()
            if now - last_command_broadcast_time > 3.0:
                last_command_broadcast_time = now
                voices_msg = f"🎙️ Available TTS Voice Presets: [{config.voice_presets}]. Type !myvoice <voicename> to set your signature voice!"
                broadcast_event("chat_message", {"user": "System", "message": voices_msg, "timestamp": time.time()})
                if config.enable_chat_responses and twitch_bot:
                    twitch_bot.send_chat(voices_msg)
            return

        # Command: !myvoice / !voice
        if raw_lower.startswith("!myvoice") or raw_lower.startswith("!voice"):
            parts = raw_text.strip().split(maxsplit=1)
            requested_voice = parts[1].strip() if len(parts) > 1 else ""
            user_name = user or "Chatter"

            if not requested_voice:
                curr_voice = user_voice_manager.get_voice(user_name) or config.tts_voice
                msg_text = f"@{user_name} Usage: !myvoice <voicename> or !myvoice reset. Your active voice: '{curr_voice}'. Presets: {config.voice_presets}"
                broadcast_event("chat_message", {"user": "System", "message": msg_text, "timestamp": time.time()})
                if config.enable_chat_responses and twitch_bot:
                    twitch_bot.send_chat(msg_text)
                return

            saved_voice = user_voice_manager.set_voice(user_name, requested_voice)
            if saved_voice == "default" or requested_voice.lower() in ("reset", "clear", "default", "none"):
                user_voice_manager.clear_user(user_name)
                msg_text = f"Reset @{user_name}'s signature TTS voice to global default ('{config.tts_voice}')."
            else:
                msg_text = f"Saved signature TTS voice for @{user_name} to '{saved_voice}'!"

            broadcast_event("chat_message", {"user": "System", "message": msg_text, "timestamp": time.time()})
            if config.enable_chat_responses and twitch_bot:
                twitch_bot.send_chat(msg_text)

            broadcast_event("status", {
                "channel": config.twitch_channel,
                "connected": bool(twitch_bot and twitch_bot.running and twitch_bot.channel),
                "authenticated": bool(twitch_bot and twitch_bot.is_authenticated),
                "config": config.to_dict(),
                "user_voices": user_voice_manager.get_all()
            })
            return

    if user:
        if "{user}" in config.user_template and "{text}" in config.user_template:
            try:
                text_to_speak = config.user_template.format(user=user, text=raw_text)
            except Exception:
                text_to_speak = f"{user} sanoo: {raw_text}"
        else:
            text_to_speak = f"{user} {config.user_template} {raw_text}"
    else:
        text_to_speak = raw_text

    chunks = process_message_to_chunks(text_to_speak, max_chars=config.max_chunk_chars, min_chars=config.min_chunk_chars)
    if not chunks:
        return

    logger.info(f"Processing text from '{user}': '{text_to_speak[:40]}' -> {len(chunks)} chunks")

    user_saved_voice = user_voice_manager.get_voice(user)
    for chunk in chunks:
        # Determine voice override hierarchy:
        # 1. Inline per-chunk tag ([alice])
        # 2. Manual test console override parameter
        # 3. User's saved signature voice (!myvoice)
        # 4. Global default config voice
        voice_to_use = chunk.voice or override_voice or user_saved_voice or config.tts_voice
        model_to_use = override_model or config.tts_model
        
        try:
            audio_bytes, mime_type = tts_client.synthesize(
                text=chunk.text,
                voice=voice_to_use,
                model=model_to_use,
                audio_format=config.tts_format
            )
            
            chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
            item_meta = {
                "id": chunk_id,
                "user": user,
                "text": chunk.text,
                "voice": voice_to_use or "default",
                "chunk_index": chunk.chunk_index + 1,
                "total_chunks": chunk.total_chunks,
                "url": f"/api/audio/{chunk_id}",
                "mime_type": mime_type,
                "created_at": time.time()
            }
            
            # Store audio
            audio_store[chunk_id] = (audio_bytes, mime_type, item_meta)
            audio_queue.append(item_meta)
            
            # Clean up old audio from store if > 100 items
            if len(audio_store) > 100:
                oldest_id = list(audio_store.keys())[0]
                del audio_store[oldest_id]
                
            # Broadcast to web audio player
            broadcast_event("audio_chunk", item_meta)
            
        except Exception as e:
            logger.error(f"Failed to synthesize chunk '{chunk.text}': {e}")
            broadcast_event("error", {"message": f"TTS synthesis failed for '{chunk.text}': {str(e)}"})


def on_twitch_message(user: str, message: str):
    """Callback triggered by Twitch IRC listener."""
    broadcast_event("chat_message", {"user": user, "message": message, "timestamp": time.time()})
    process_incoming_text(user=user, raw_text=message)


class TTSRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Quiet standard HTTP logs to avoid spam
        pass

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Route: SSE Event Stream
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._send_cors_headers()
            self.end_headers()

            client_q = queue.Queue()
            sse_clients.append(client_q)

            # Send initial status
            init_payload = f"event: status\ndata: {json.dumps(self._get_status_dict())}\n\n"
            try:
                self.wfile.write(init_payload.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                if client_q in sse_clients:
                    sse_clients.remove(client_q)
                return

            try:
                while True:
                    try:
                        msg = client_q.get(timeout=450)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Heartbeat ping to keep SSE connection open
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                if client_q in sse_clients:
                    sse_clients.remove(client_q)
            return

        # Route: Stream Audio File
        if path.startswith("/api/audio/"):
            chunk_id = path.split("/api/audio/")[-1]
            if chunk_id in audio_store:
                audio_bytes, mime_type, _ = audio_store[chunk_id]
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(audio_bytes)
                return
            else:
                self.send_error(404, "Audio chunk not found")
                return

        # Route: Auth Status
        if path == "/api/auth/status":
            tok = self._get_request_auth_token()
            authenticated = dashboard_auth_manager.verify_session(tok)
            self._send_json(200, {
                "auth_required": dashboard_auth_manager.is_auth_required(),
                "authenticated": authenticated,
                "twitch_auth": twitch_bot.get_auth_info() if twitch_bot else {}
            })
            return

        # Route: API Status
        if path == "/api/status":
            self._send_json(200, self._get_status_dict())
            return

        # Route: User Voices List
        if path == "/api/user_voices":
            self._send_json(200, {"user_voices": user_voice_manager.get_all()})
            return

        # Route: Proxy GET /api/tts
        if path == "/api/tts":
            text = query.get("text", [""])[0]
            voice = query.get("voice", [None])[0]
            model = query.get("model", [None])[0]
            fmt = query.get("format", [None])[0]
            
            if not text:
                self._send_json(400, {"error": "Missing required parameter 'text'"})
                return
                
            try:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=text, voice=voice, model=model, audio_format=fmt, method="GET"
                )
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(audio_bytes)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # Serve static files (HTML, CSS, JS)
        if path == "/" or path == "/index.html":
            file_path = os.path.join(STATIC_DIR, "index.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return
            
        rel_path = path.lstrip('/')
        safe_path = os.path.join(STATIC_DIR, rel_path)
        if os.path.isfile(safe_path) and os.path.abspath(safe_path).startswith(os.path.abspath(STATIC_DIR)):
            mime = "text/css" if path.endswith(".css") else ("application/javascript" if path.endswith(".js") else "text/plain")
            self._serve_static_file(safe_path, mime)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(post_data.decode('utf-8')) if post_data else {}
        except Exception:
            body = {}

        # Route: Validate Twitch Token (Public/Auth tool)
        if path == "/api/auth/validate_twitch":
            token = body.get("oauth_token", "").strip()
            res = twitch_token_validator.validate_token(token)
            self._send_json(200, res)
            return

        # Route: Admin Login
        if path == "/api/auth/login":
            password = body.get("password", "").strip()
            success, session_token, err = dashboard_auth_manager.authenticate(password)
            if success:
                self._send_json(200, {"success": True, "token": session_token})
            else:
                self._send_json(401, {"error": err or "Invalid password"})
            return

        # Route: Admin Logout
        if path == "/api/auth/logout":
            tok = self._get_request_auth_token()
            dashboard_auth_manager.revoke_session(tok)
            self._send_json(200, {"success": True})
            return

        # Route: Proxy POST /api/tts
        if path == "/api/tts":
            text = body.get("text", "")
            voice = body.get("voice")
            model = body.get("model")
            fmt = body.get("format")
            
            if not text:
                self._send_json(400, {"error": "Missing required field 'text'"})
                return
                
            try:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=text, voice=voice, model=model, audio_format=fmt, method="POST"
                )
                if fmt == "json":
                    import base64
                    b64 = base64.b64encode(audio_bytes).decode('ascii')
                    self._send_json(200, {"audio": b64, "mime_type": mime_type})
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Content-Length", str(len(audio_bytes)))
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(audio_bytes)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # Protected administrative routes below
        if not self._check_auth():
            return

        # Route: Connect Twitch Channel
        if path == "/api/connect":
            channel = body.get("channel", "").strip()
            if not channel:
                self._send_json(400, {"error": "Channel name is required"})
                return
            config.twitch_channel = channel
            config.save()
            if twitch_bot:
                twitch_bot.set_channel(channel)
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "channel": channel})
            return

        # Route: Send Helpful Info Now to Chat
        if path == "/api/bot/send_info":
            info_msg = send_bot_helpful_info()
            self._send_json(200, {"success": True, "message": info_msg})
            return

        # Route: Force Reconnect Twitch Bot
        if path == "/api/bot/reconnect":
            if twitch_bot:
                twitch_bot.reconnect()
                broadcast_event("status", self._get_status_dict())
                self._send_json(200, {"success": True, "message": "Twitch bot reconnection triggered."})
            else:
                self._send_json(400, {"error": "Twitch bot is not initialized."})
            return

        # Route: Clear Audio Queue
        if path == "/api/queue/clear":
            audio_queue.clear()
            broadcast_event("clear_audio", {"user": "Dashboard", "timestamp": time.time()})
            self._send_json(200, {"success": True, "message": "Audio queue cleared."})
            return

        # Route: Manual Test TTS
        if path == "/api/tts/test":
            text = body.get("text", "").strip()
            voice = body.get("voice")
            model = body.get("model")
            user = body.get("user", "TestUser")
            
            if not text:
                self._send_json(400, {"error": "Text is required"})
                return
                
            threading.Thread(
                target=process_incoming_text,
                kwargs={"user": user, "raw_text": text, "override_voice": voice, "override_model": model},
                daemon=True
            ).start()
            
            self._send_json(200, {"success": True, "message": "Test TTS job queued."})
            return

        # Route: Save Config/Settings
        if path == "/api/settings":
            if "tts_api_url" in body:
                config.tts_api_url = str(body["tts_api_url"]).strip()
                tts_client.base_url = config.tts_api_url.rstrip('/')
            if "tts_voice" in body:
                config.tts_voice = str(body["tts_voice"]).strip()
            if "tts_model" in body:
                config.tts_model = str(body["tts_model"]).strip()
            if "tts_format" in body:
                config.tts_format = str(body["tts_format"]).strip()
            if "max_chunk_chars" in body:
                config.max_chunk_chars = int(body["max_chunk_chars"])
            if "min_chunk_chars" in body:
                config.min_chunk_chars = int(body["min_chunk_chars"])
            if "user_template" in body:
                config.user_template = str(body["user_template"]).strip()
            if "voice_presets" in body:
                config.voice_presets = str(body["voice_presets"]).strip()
            if "twitch_bot_username" in body:
                config.twitch_bot_username = str(body["twitch_bot_username"]).strip()
            if "twitch_oauth_token" in body:
                raw_tok = str(body["twitch_oauth_token"]).strip()
                # Don't update if sent masked string unless it changed
                if not raw_tok.startswith("oauth:••••") and not raw_tok.startswith("••••"):
                    config.twitch_oauth_token = raw_tok
            if "enable_chat_responses" in body:
                config.enable_chat_responses = bool(body["enable_chat_responses"])
            if "enable_periodic_info" in body:
                config.enable_periodic_info = bool(body["enable_periodic_info"])
            if "periodic_info_interval" in body:
                config.periodic_info_interval = int(body["periodic_info_interval"])
            if "admin_password" in body:
                raw_pwd = str(body["admin_password"]).strip()
                if raw_pwd != "••••••••":
                    config.admin_password = raw_pwd
            if "twitch_client_id" in body:
                config.twitch_client_id = str(body["twitch_client_id"]).strip()
            
            config.save()
            if twitch_bot:
                twitch_bot.set_credentials(config.twitch_bot_username, config.twitch_oauth_token)
            
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "config": self._get_config_dict()})
            return

        # Route: User Voices Management
        if path == "/api/user_voices/set":
            username = body.get("user", "").strip()
            voice = body.get("voice", "").strip()
            if not username or not voice:
                self._send_json(400, {"error": "Both 'user' and 'voice' parameters are required"})
                return
            saved = user_voice_manager.set_voice(username, voice)
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "user": username, "voice": saved, "user_voices": user_voice_manager.get_all()})
            return

        if path == "/api/user_voices/delete":
            username = body.get("user", "").strip()
            if not username:
                self._send_json(400, {"error": "Parameter 'user' is required"})
                return
            user_voice_manager.clear_user(username)
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "user_voices": user_voice_manager.get_all()})
            return

        if path == "/api/user_voices/clear":
            user_voice_manager.clear_all()
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "user_voices": {}})
            return

        self.send_error(404, "Not Found")

    def _get_status_dict(self) -> dict:
        return {
            "channel": config.twitch_channel,
            "connected": bool(twitch_bot and twitch_bot.running and twitch_bot.channel),
            "authenticated": bool(twitch_bot and twitch_bot.is_authenticated),
            "config": self._get_config_dict(),
            "user_voices": user_voice_manager.get_all(),
            "auth_required": dashboard_auth_manager.is_auth_required(),
            "twitch_auth": twitch_bot.get_auth_info() if twitch_bot else {},
            "bot_status": twitch_bot.get_status() if twitch_bot else {}
        }

    def _get_config_dict(self) -> dict:
        return config.to_masked_dict()

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_static_file(self, filepath: str, mime_type: str):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading static file: {e}")


def run_server(host: str = "0.0.0.0", port: int = 5000):
    global twitch_bot
    
    # Initialize Twitch bot listener
    twitch_bot = TwitchListener(
        on_message=on_twitch_message,
        bot_username=config.twitch_bot_username,
        oauth_token=config.twitch_oauth_token
    )
    twitch_bot.start(channel=config.twitch_channel)
    
    # Start periodic helpful info background thread
    p_thread = threading.Thread(target=_periodic_info_loop, daemon=True)
    p_thread.start()

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TTSRequestHandler)
    logger.info(f"Twitch TTS Bot Web Server running on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping server...")
    finally:
        if twitch_bot:
            twitch_bot.stop()
        httpd.server_close()
