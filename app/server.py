import base64
import json
import logging
import os
import queue
import random
import re
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Tuple, List, Optional
import urllib.parse

from app.config import config, BASE_DIR
from app.text_chunker import process_message_to_chunks, TTSChunk
from app.tts_client import tts_client, TTSClient
from app.twitch_listener import TwitchListener
from app.user_voices import user_voice_manager
from app.soundboard import soundboard_manager
from app.kill_counter import kill_counter_monitor
from app.auth import dashboard_auth_manager, twitch_token_validator, mask_token, hash_password
from app.rate_limiter import login_limiter, tts_limiter, counter_limiter, soundboard_limiter, validate_limiter
from app.sanitizer import (
    sanitize_string,
    sanitize_username,
    sanitize_channels_list,
    sanitize_identifier,
    sanitize_int,
    sanitize_bool,
    sanitize_audio_format,
    sanitize_url,
    sanitize_tts_url,
    sanitize_float,
    sanitize_speaker_name_for_tts,
    validate_and_sanitize_audio_upload,
    verify_streamer_password,
)
from app.chat_commands import parse_chat_command, match_voice_preset, match_voice_action, get_commands_catalog


logger = logging.getLogger("Server")

# Global Audio Storage & Queue
# audio_id -> (bytes, mime_type, metadata_dict)
audio_store: Dict[str, Tuple[bytes, str, dict]] = {}
audio_queue: List[dict] = []

# Event subscriptions (SSE): list of (queue, filter_channel, client_ip, is_admin) tuples
sse_clients: List[Tuple[queue.Queue, Optional[str], Optional[str], bool]] = []

# SSE connection limits (OWASP API4:2023 - Unrestricted Resource Consumption)
MAX_SSE_CLIENTS = 50
MAX_SSE_PER_IP = 5

# Twitch Listener instance
twitch_bot: Optional[TwitchListener] = None

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def get_public_status_dict() -> dict:
    """Return sanitized status dict safe for internet exposure (no admin creds, no infrastructure, no TTS API URL)."""
    return {
        "channel": config.twitch_channel,
        "channels": config.channels,
        "connected": bool(twitch_bot and twitch_bot.running and (twitch_bot.channels or twitch_bot.channel)),
        "authenticated": bool(twitch_bot and twitch_bot.is_authenticated),
        "config": config.to_public_dict(),
        "user_voices": user_voice_manager.get_all(),
        "auth_required": dashboard_auth_manager.is_auth_required(),
        "counter": {
            "enabled": bool(config.enable_kill_counter),
            "count": kill_counter_monitor.current_count,
        }
    }


def extract_upload_payload(headers: dict, post_data: bytes, body: dict) -> Tuple[bytes, str, Optional[str], str]:
    """
    Extract file_bytes, filename, custom_sound_name, and streamer password from JSON base64 or multipart form payload.
    """
    filename = ""
    custom_sound_name = None
    password = ""
    file_bytes = b""

    # 1. Base64 JSON payload
    if body and ("file_b64" in body or "file_base64" in body or "data" in body):
        raw_b64 = body.get("file_b64") or body.get("file_base64") or body.get("data") or ""
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[-1]
        try:
            file_bytes = base64.b64decode(raw_b64.strip())
        except Exception:
            file_bytes = b""
        filename = sanitize_string(body.get("filename") or body.get("name") or "sound.mp3")
        custom_sound_name = body.get("sound_name") or body.get("title")
        password = body.get("password") or body.get("streamer_password") or body.get("code") or ""
        return file_bytes, filename, custom_sound_name, str(password)

    # 2. Multipart form data
    content_type = headers.get("Content-Type", "")
    if "multipart/form-data" in content_type:
        boundary_match = re.search(r'boundary=([^;]+)', content_type, re.IGNORECASE)
        if boundary_match:
            boundary = boundary_match.group(1).strip('"').encode('utf-8')
            parts = post_data.split(b'--' + boundary)
            for part in parts:
                if not part or part.startswith(b'--'):
                    continue
                header_data, _, part_body = part.partition(b'\r\n\r\n')
                part_body = part_body.rstrip(b'\r\n')
                header_text = header_data.decode('utf-8', errors='ignore')

                disp_match = re.search(r'Content-Disposition:\s*form-data;\s*name="([^"]+)"(?:;\s*filename="([^"]+)")?', header_text, re.IGNORECASE)
                if disp_match:
                    field_name = disp_match.group(1)
                    fname = disp_match.group(2)
                    if field_name == "file" and fname:
                        file_bytes = part_body
                        filename = fname
                    elif field_name in ("password", "streamer_password", "code"):
                        password = part_body.decode('utf-8', errors='ignore').strip()
                    elif field_name == "sound_name":
                        custom_sound_name = part_body.decode('utf-8', errors='ignore').strip()

    return file_bytes, filename, custom_sound_name, str(password)



def broadcast_event(event_type: str, payload: dict, admin_only: bool = False):
    """Send SSE event to connected web clients, filtered by channel and client permission level."""
    event_chan = payload.get("channel")
    event_chan_clean = str(event_chan).strip().lstrip("#").lower() if event_chan else None

    to_remove = []
    for item in sse_clients:
        if isinstance(item, tuple):
            q = item[0]
            filter_chan = item[1] if len(item) > 1 else None
            client_ip = item[2] if len(item) > 2 else None
            is_admin = item[3] if len(item) > 3 else True
        else:
            q, filter_chan, client_ip, is_admin = item, None, None, True

        if admin_only and not is_admin:
            continue

        if filter_chan:
            # Client requested strict channel filtering (e.g. /obs?channel=channelname)
            if event_chan_clean:
                if filter_chan != event_chan_clean:
                    continue
            elif event_type in ("audio_chunk", "chat_message", "skip_audio", "clear_audio", "soundboard_trigger"):
                # Channel-specific event without a matching channel tag must not leak to a channel-filtered client
                continue

        # Filter admin-level status payload from public SSE clients (CWE-200)
        if event_type == "status" and not is_admin:
            client_payload = get_public_status_dict()
        else:
            client_payload = payload

        msg = f"event: {event_type}\ndata: {json.dumps(client_payload)}\n\n"

        try:
            q.put_nowait(msg)
        except Exception:
            to_remove.append(item)

    for item in to_remove:
        if item in sse_clients:
            sse_clients.remove(item)


def handle_sse_stream(handler, is_admin: bool = False):
    """Handle SSE event stream connection for a request handler."""
    if hasattr(handler, "_get_client_ip"):
        client_ip = handler._get_client_ip()
    elif getattr(handler, "client_address", None):
        client_ip = handler.client_address[0]
    else:
        client_ip = "unknown"

    # SSE connection limits (OWASP API4:2023)
    if len(sse_clients) >= MAX_SSE_CLIENTS:
        if hasattr(handler, "_send_json"):
            handler._send_json(503, {"error": "Too many active connections. Try again later."})
        else:
            body = json.dumps({"error": "Too many active connections. Try again later."}).encode("utf-8")
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        return

    ip_count = sum(1 for item in sse_clients if isinstance(item, tuple) and len(item) >= 3 and item[2] == client_ip)
    if ip_count >= MAX_SSE_PER_IP:
        if hasattr(handler, "_send_json"):
            handler._send_json(429, {"error": "Too many connections from this IP."})
        else:
            body = json.dumps({"error": "Too many connections from this IP."}).encode("utf-8")
            handler.send_response(429)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        return

    parsed = urllib.parse.urlparse(handler.path)
    query = urllib.parse.parse_qs(parsed.query)
    req_chan = query.get("channel", [None])[0] or query.get("ch", [None])[0]
    filter_chan = req_chan.strip().lstrip('#').lower() if req_chan else None

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    if hasattr(handler, "_send_cors_headers"):
        handler._send_cors_headers()
    if hasattr(handler, "_send_security_headers"):
        try:
            handler._send_security_headers(allow_framing=True)
        except TypeError:
            handler._send_security_headers()
    handler.end_headers()

    client_q = queue.Queue()
    client_item = (client_q, filter_chan, client_ip, is_admin)
    sse_clients.append(client_item)

    if is_admin and hasattr(handler, "_get_status_dict"):
        init_status = handler._get_status_dict()
    else:
        init_status = get_public_status_dict()

    init_payload = f"event: status\ndata: {json.dumps(init_status)}\n\n"
    try:
        handler.wfile.write(init_payload.encode("utf-8"))
        handler.wfile.flush()
    except Exception:
        if client_item in sse_clients:
            sse_clients.remove(client_item)
        return

    try:
        while True:
            try:
                msg = client_q.get(timeout=450)
                handler.wfile.write(msg.encode("utf-8"))
                handler.wfile.flush()
            except queue.Empty:
                handler.wfile.write(b": ping\n\n")
                handler.wfile.flush()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        if client_item in sse_clients:
            sse_clients.remove(client_item)


def get_random_preset_voice() -> str:
    """Return a random voice from available preset voices or fallback default."""
    presets = [v.strip() for v in config.voice_presets.replace(';', ',').split(',') if v.strip()]
    if presets:
        return random.choice(presets)
    return config.tts_voice or "default"


def send_bot_helpful_info() -> str:
    """Send helpful info about TTS bot features & commands to chat & SSE UI."""
    presets_str = config.voice_presets if config.voice_presets else "none"
    info_text = (
        f"🎙️ Twitch TTS Bot Info & Commands: "
        f"!myvoice <voice|random|reset> (Presets: [{presets_str}]) | "
        f"!voices | !sounds (trigger (soundname)) | !skip | !clear | "
        f"!pieruta <user> | Tags: [voice] multi-voice, {{8D}} 8D audio. "
        f"(All commands support fuzzy auto-correction!)"
    )
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
            # Periodic security cleanup
            dashboard_auth_manager.cleanup_expired_sessions()
            login_limiter.cleanup()
            tts_limiter.cleanup()
        except Exception as e:
            logger.error(f"Error in periodic info loop: {e}")


last_command_broadcast_time = 0.0
last_speaker: Optional[str] = None
last_speaker_time: float = 0.0
pieruta_targets: Dict[str, bool] = {}

def mix_audio_with_background(tts_audio_bytes: bytes, bg_file_path: str, audio_format: str = "wav") -> Tuple[bytes, str]:
    """
    Mixes tts_audio_bytes with a background audio file (e.g. fartbackground.mp3) using ffmpeg amix.
    Returns tuple of (mixed_audio_bytes, mime_type).
    """
    if not bg_file_path or not os.path.exists(bg_file_path):
        fmt = audio_format or "wav"
        mime = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
        return tts_audio_bytes, mime

    fmt = audio_format or "wav"
    out_fmt = "wav" if fmt not in ("mp3", "wav", "ogg") else fmt
    mime_type = "audio/mpeg" if out_fmt == "mp3" else f"audio/{out_fmt}"

    tts_tmp = None
    out_tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{out_fmt}", delete=False) as f:
            f.write(tts_audio_bytes)
            tts_tmp = f.name

        out_tmp = tts_tmp + f"_mixed.{out_fmt}"

        cmd = [
            "ffmpeg", "-y",
            "-i", tts_tmp,
            "-stream_loop", "-1",
            "-i", bg_file_path,
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "[aout]",
            "-f", out_fmt,
            out_tmp
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if res.returncode == 0 and os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            with open(out_tmp, "rb") as f:
                mixed_bytes = f.read()
            logger.info(f"⚡ ffmpeg mixed TTS audio with background sound '{os.path.basename(bg_file_path)}' ({len(mixed_bytes)} bytes).")
            return mixed_bytes, mime_type
        else:
            logger.warning(f"ffmpeg mixing warning (exit code {res.returncode}): {res.stderr.decode('utf-8', errors='ignore')}")
            return tts_audio_bytes, mime_type
    except Exception as e:
        logger.error(f"Error mixing audio with ffmpeg: {e}")
        return tts_audio_bytes, mime_type
    finally:
        if tts_tmp and os.path.exists(tts_tmp):
            try:
                os.remove(tts_tmp)
            except Exception:
                pass
        if out_tmp and os.path.exists(out_tmp):
            try:
                os.remove(out_tmp)
            except Exception:
                pass


def apply_8d_audio_effect(audio_bytes: bytes, audio_format: str = "wav", speed: Optional[float] = None) -> Tuple[bytes, str]:
    """
    Applies an 8D spatial panning and audio atmosphere effect using ffmpeg apulsator and aecho filters.
    Returns tuple of (processed_audio_bytes, mime_type).
    """
    if not audio_bytes:
        fmt = audio_format or "wav"
        mime = "audio/mpeg" if fmt == "mp3" else f"audio/{fmt}"
        return audio_bytes, mime

    if speed is None:
        speed = getattr(config, "effect_8d_speed", 0.15)
    try:
        speed_val = float(speed)
    except (ValueError, TypeError):
        speed_val = 0.15
    speed_val = max(0.01, min(5.0, speed_val))

    fmt = audio_format or "wav"
    out_fmt = "wav" if fmt not in ("mp3", "wav", "ogg") else fmt
    mime_type = "audio/mpeg" if out_fmt == "mp3" else f"audio/{out_fmt}"

    in_tmp = None
    out_tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{out_fmt}", delete=False) as f:
            f.write(audio_bytes)
            in_tmp = f.name

        out_tmp = in_tmp + f"_8d.{out_fmt}"

        filter_str = f"apulsator=hz={speed_val}:mode=sine:offset_l=0:offset_r=0.5:amount=1,aecho=0.8:0.88:40:0.2"

        cmd = [
            "ffmpeg", "-y",
            "-i", in_tmp,
            "-filter_complex", f"[0:a]{filter_str}[aout]",
            "-map", "[aout]",
            "-f", out_fmt,
            out_tmp
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if res.returncode == 0 and os.path.exists(out_tmp) and os.path.getsize(out_tmp) > 0:
            with open(out_tmp, "rb") as f:
                processed_bytes = f.read()
            logger.info(f"🌀 Applied 8D audio effect via ffmpeg ({len(processed_bytes)} bytes).")
            return processed_bytes, mime_type
        else:
            logger.warning(f"ffmpeg 8D effect warning (exit code {res.returncode}): {res.stderr.decode('utf-8', errors='ignore')}")
            return audio_bytes, mime_type
    except Exception as e:
        logger.error(f"Error applying 8D audio effect with ffmpeg: {e}")
        return audio_bytes, mime_type
    finally:
        if in_tmp and os.path.exists(in_tmp):
            try:
                os.remove(in_tmp)
            except Exception:
                pass
        if out_tmp and os.path.exists(out_tmp):
            try:
                os.remove(out_tmp)
            except Exception:
                pass

def serve_darkcounter_lua(handler, query: dict):
    """Serve darkcounter_obs.lua script with dynamic query parameter customization."""
    lua_path = os.path.join(BASE_DIR, "darkcounter_obs.lua")
    if not os.path.exists(lua_path):
        handler.send_error(404, "Script not found")
        return
    
    try:
        with open(lua_path, "r", encoding="utf-8") as f:
            lua_content = f.read()

        req_chan = query.get("channel", [""])[0].strip().lstrip('#').lower() if query.get("channel") else ""
        req_url = query.get("server_url", [""])[0].strip() if query.get("server_url") else ""
        req_token = query.get("api_token", [""])[0].strip() if query.get("api_token") else ""
        req_file = query.get("counter_file", [""])[0].strip() if query.get("counter_file") else ""

        if not req_url and handler.headers.get("Host"):
            proto = handler.headers.get("X-Forwarded-Proto", "http").lower()
            if hasattr(handler, "is_https") and handler.is_https:
                proto = "https"
            req_url = f"{proto}://{handler.headers.get('Host')}"

        if req_chan:
            lua_content = re.sub(r'local channel = "[^"]*"', f'local channel = "{req_chan}"', lua_content)
            lua_content = re.sub(r'obs_data_set_default_string\(settings, "channel", "[^"]*"\)', f'obs_data_set_default_string(settings, "channel", "{req_chan}")', lua_content)

        if req_url:
            lua_content = re.sub(r'local server_url = "[^"]*"', f'local server_url = "{req_url}"', lua_content)
            lua_content = re.sub(r'obs_data_set_default_string\(settings, "server_url", "[^"]*"\)', f'obs_data_set_default_string(settings, "server_url", "{req_url}")', lua_content)

        if req_token:
            lua_content = re.sub(r'local api_token = "[^"]*"', f'local api_token = "{req_token}"', lua_content)
            lua_content = re.sub(r'obs_data_set_default_string\(settings, "api_token", "[^"]*"\)', f'obs_data_set_default_string(settings, "api_token", "{req_token}")', lua_content)

        if req_file:
            lua_content = re.sub(r'local counter_file = "[^"]*"', f'local counter_file = "{req_file}"', lua_content)
            lua_content = re.sub(r'obs_data_set_default_string\(settings, "counter_file", "[^"]*"\)', f'obs_data_set_default_string(settings, "counter_file", "{req_file}")', lua_content)

        encoded = lua_content.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/x-lua; charset=utf-8")
        handler.send_header("Content-Disposition", 'attachment; filename="darkcounter_obs.lua"')
        handler.send_header("Content-Length", str(len(encoded)))
        if hasattr(handler, "_send_cors_headers"):
            handler._send_cors_headers()
        handler.end_headers()
        handler.wfile.write(encoded)
    except Exception as e:
        logger.error(f"Error serving darkcounter_obs.lua: {e}")
        handler.send_error(500, "Internal Server Error")


def process_incoming_text(user: str, raw_text: str, override_voice: Optional[str] = None, override_model: Optional[str] = None, channel: str = "", is_death_counter: bool = False):
    """
    Process incoming chat or test message:
    1. Intercept chat commands (!help, !tts, !botinfo, !voices, !myvoice, !skip, !clear).
    2. Prepend user template to regular text (unless sent back-to-back by same user).
    3. Parse into chunks (with per-chunk voice tags if present).
    4. Request local TTS API for each chunk.
    5. Save audio to memory store and notify frontend player via SSE.
    """
    global last_command_broadcast_time, last_speaker, last_speaker_time

    clean_chan = channel.strip().lstrip('#').lower() if channel else (config.channels[0] if config.channels else "")

    has_8d = False
    if raw_text:
        if re.search(r'\{\s*8d\s*\}', raw_text, re.IGNORECASE):
            has_8d = True
            raw_text = re.sub(r'\{\s*8d\s*\}', '', raw_text, flags=re.IGNORECASE).strip()
            logger.info(f"🌀 Detected {{8D}} tag in message from '{user}'. Enabling 8D audio effect.")

        parsed_cmd = parse_chat_command(raw_text)
        if parsed_cmd:
            cmd_name, cmd_args, _score = parsed_cmd

            if cmd_name == "pieruta":
                raw_target_arg = cmd_args.strip()
                if not raw_target_arg:
                    msg_text = "💨 Usage: !pieruta <username>"
                else:
                    target_user = sanitize_identifier(raw_target_arg.lstrip('@'), max_len=100)
                    if target_user:
                        pieruta_targets[target_user.lower()] = True
                        msg_text = f"💨 Fart background sound queued for @{target_user}'s next TTS message!"
                        logger.info(f"Chat command '!pieruta' set fartbackground target for user '{target_user}'.")
                    else:
                        msg_text = "💨 Invalid username specified."

                broadcast_event("chat_message", {"user": "System", "message": msg_text, "channel": clean_chan, "timestamp": time.time()})
                if config.enable_chat_responses and twitch_bot:
                    twitch_bot.send_chat(msg_text, channel=clean_chan)
                return

            elif cmd_name == "skip":
                logger.info(f"Chat command '!skip' received from user '{user}'.")
                broadcast_event("skip_audio", {"user": user, "channel": clean_chan, "timestamp": time.time()})
                skip_msg = f"⏭️ Audio skipped by @{user}." if user else "⏭️ Audio skipped."
                broadcast_event("chat_message", {"user": "System", "message": skip_msg, "channel": clean_chan, "timestamp": time.time()})
                if config.enable_chat_responses and twitch_bot:
                    twitch_bot.send_chat(skip_msg, channel=clean_chan)
                return

            elif cmd_name == "clear":
                logger.info(f"Chat command '!clear' received from user '{user}'.")
                audio_queue.clear()
                broadcast_event("clear_audio", {"user": user, "channel": clean_chan, "timestamp": time.time()})
                clear_msg = f"🛑 Audio queue cleared by @{user}." if user else "🛑 Audio queue cleared."
                broadcast_event("chat_message", {"user": "System", "message": clear_msg, "channel": clean_chan, "timestamp": time.time()})
                if config.enable_chat_responses and twitch_bot:
                    twitch_bot.send_chat(clear_msg, channel=clean_chan)
                return

            elif cmd_name == "help":
                now = time.time()
                if now - last_command_broadcast_time > 3.0:
                    last_command_broadcast_time = now
                    send_bot_helpful_info()
                return

            elif cmd_name == "voices":
                now = time.time()
                if now - last_command_broadcast_time > 3.0:
                    last_command_broadcast_time = now
                    voices_msg = f"🎙️ Available TTS Voice Presets: [{config.voice_presets}]. Type !myvoice <voicename> to set your signature voice!"
                    broadcast_event("chat_message", {"user": "System", "message": voices_msg, "channel": clean_chan, "timestamp": time.time()})
                    if config.enable_chat_responses and twitch_bot:
                        twitch_bot.send_chat(voices_msg, channel=clean_chan)
                return

            elif cmd_name == "sounds":
                now = time.time()
                if now - last_command_broadcast_time > 3.0:
                    last_command_broadcast_time = now
                    available_sounds = list(soundboard_manager.get_available_sounds().keys())
                    if available_sounds:
                        sounds_str = ", ".join(available_sounds[:25])
                        sb_msg = f"🔊 Available sound effects: {sounds_str}. Type (soundname) in chat to play!"
                        tts_speech = f"Saatavilla olevat ääniefektit ovat: {sounds_str}"
                    else:
                        sb_msg = f"🔊 Soundboard is active! Add soundboard .mp3 files into {soundboard_manager.directory} to play them using (soundname) in chat."
                        tts_speech = "Soundboardilla ei ole vielä ääniefektejä."

                    broadcast_event("chat_message", {"user": "System", "message": sb_msg, "channel": clean_chan, "timestamp": time.time()})
                    if config.enable_chat_responses and twitch_bot:
                        twitch_bot.send_chat(sb_msg, channel=clean_chan)

                    # Synthesize and speak available sound effect filenames aloud via TTS
                    process_incoming_text(user=None, raw_text=tts_speech, channel=clean_chan)
                return

            elif cmd_name == "myvoice":
                raw_voice_arg = cmd_args.strip()
                user_name = user or "Chatter"

                if user_voice_manager.is_locked(user_name):
                    msg_text = f"🔒 @{user_name}, your signature voice is locked by the streamer and cannot be changed."
                    broadcast_event("chat_message", {"user": "System", "message": msg_text, "channel": clean_chan, "timestamp": time.time()})
                    if config.enable_chat_responses and twitch_bot:
                        twitch_bot.send_chat(msg_text, channel=clean_chan)
                    return

                if not raw_voice_arg:
                    curr_voice = user_voice_manager.get_voice(user_name) or config.tts_voice
                    msg_text = f"@{user_name} Usage: !myvoice <voicename>, !myvoice random, or !myvoice reset. Your active voice: '{curr_voice}'. Presets: {config.voice_presets}"
                    broadcast_event("chat_message", {"user": "System", "message": msg_text, "channel": clean_chan, "timestamp": time.time()})
                    if config.enable_chat_responses and twitch_bot:
                        twitch_bot.send_chat(msg_text, channel=clean_chan)
                    return

                action_match = match_voice_action(raw_voice_arg)
                if action_match and action_match[0] == "random":
                    chosen_voice = get_random_preset_voice()
                    saved_voice = user_voice_manager.set_voice(user_name, chosen_voice)
                    msg_text = f"🎲 Picked random signature TTS voice for @{user_name}: '{saved_voice}'!"
                elif action_match and action_match[0] == "reset":
                    user_voice_manager.clear_user(user_name)
                    msg_text = f"Reset @{user_name}'s signature TTS voice to global default ('{config.tts_voice}')."
                else:
                    clean_requested = sanitize_identifier(raw_voice_arg, max_len=100)
                    if not clean_requested:
                        user_voice_manager.clear_user(user_name)
                        msg_text = f"Reset @{user_name}'s signature TTS voice to global default ('{config.tts_voice}')."
                    else:
                        presets_list = [v.strip() for v in config.voice_presets.replace(';', ',').split(',') if v.strip()]
                        preset_match = match_voice_preset(clean_requested, presets_list)
                        if preset_match:
                            clean_requested = preset_match[0]
                        saved_voice = user_voice_manager.set_voice(user_name, clean_requested)
                        msg_text = f"Saved signature TTS voice for @{user_name} to '{saved_voice}'!"

                broadcast_event("chat_message", {"user": "System", "message": msg_text, "channel": clean_chan, "timestamp": time.time()})
                if config.enable_chat_responses and twitch_bot:
                    twitch_bot.send_chat(msg_text, channel=clean_chan)

                broadcast_event("status", {
                    "channel": config.twitch_channel,
                    "channels": config.channels,
                    "connected": bool(twitch_bot and twitch_bot.running and (twitch_bot.channels or twitch_bot.channel)),
                    "authenticated": bool(twitch_bot and twitch_bot.is_authenticated),
                    "config": config.to_public_dict(),
                    "user_voices": user_voice_manager.get_all()
                })
                return

    message_chunks = process_message_to_chunks(raw_text) if raw_text else []

    # If the message contains ONLY soundboard triggers, do not speak the chatter's name prefix with TTS.
    is_soundboard_only = bool(message_chunks) and all(c.is_soundboard for c in message_chunks)

    now = time.time()
    skip_user_prefix = False
    if is_soundboard_only:
        skip_user_prefix = True

    if user and last_speaker and not is_soundboard_only:
        if user.strip().lower() == last_speaker.strip().lower():
            if config.same_user_timeout > 0 and (now - last_speaker_time) <= config.same_user_timeout:
                skip_user_prefix = True

    prefix_text = ""
    if user and not skip_user_prefix:
        tts_user = sanitize_speaker_name_for_tts(user)
        if "{user}" in config.user_template:
            if "{text}" in config.user_template:
                prefix_template = config.user_template.split("{text}")[0].strip()
                prefix_text = prefix_template.replace("{user}", tts_user).strip()
            else:
                prefix_text = config.user_template.replace("{user}", tts_user).strip()
        else:
            prefix_text = f"{tts_user} {config.user_template}".strip()

    if user and not is_soundboard_only:
        last_speaker = user
        last_speaker_time = now
    elif not user:
        last_speaker = None
        last_speaker_time = 0.0

    prefix_chunks = process_message_to_chunks(prefix_text) if prefix_text else []
    chunks = prefix_chunks + message_chunks

    if not chunks:
        return

    total = len(chunks)
    for idx, c in enumerate(chunks):
        c.chunk_index = idx
        c.total_chunks = total

    # Check for pending fartbackground trigger for this speaker
    has_fart_bg = False
    if user:
        clean_user_key = user.strip().lower()
        if pieruta_targets.pop(clean_user_key, False):
            has_fart_bg = True
            logger.info(f"💨 Applying fartbackground audio effect for target user '{user}'.")

    logger.info(f"Processing text from '{user}' [#{clean_chan}]: '{raw_text[:40]}' -> {len(chunks)} segments")

    user_saved_voice = user_voice_manager.get_voice(user)

    def emit_chunk(item_meta: dict):
        audio_queue.append(item_meta)
        while len(audio_queue) > 200:
            audio_queue.pop(0)
        while len(audio_store) > 200:
            oldest_id = next(iter(audio_store))
            del audio_store[oldest_id]
        broadcast_event("audio_chunk", item_meta)

    for i, chunk in enumerate(chunks):
        # Determine voice override hierarchy:
        # 1. Inline per-chunk tag ([alice])
        # 2. Manual test console override parameter
        # 3. User's saved signature voice (!myvoice)
        # 4. Global default config voice
        voice_to_use = chunk.voice or override_voice or user_saved_voice or config.tts_voice
        if voice_to_use and voice_to_use.lower() in ("random", "rand", "rng", "satunnainen"):
            voice_to_use = get_random_preset_voice()
        model_to_use = override_model or config.tts_model
        
        try:
            if chunk.is_soundboard and chunk.sound_file and os.path.exists(chunk.sound_file):
                with open(chunk.sound_file, "rb") as f:
                    audio_bytes = f.read()
                mime_type = soundboard_manager.get_mime_type(chunk.sound_file)
                voice_used = "soundboard"
            else:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=chunk.text,
                    voice=voice_to_use,
                    model=model_to_use,
                    audio_format=config.tts_format,
                    language=config.tts_language,
                    speed=config.tts_speed,
                    num_step=config.tts_num_step,
                    guidance_scale=config.tts_guidance_scale,
                    seed=config.tts_seed
                )
                voice_used = voice_to_use or "default"

                if has_fart_bg:
                    bg_match = soundboard_manager.find_sound("fartbackground")
                    if bg_match and os.path.exists(bg_match[1]):
                        audio_bytes, mime_type = mix_audio_with_background(
                            tts_audio_bytes=audio_bytes,
                            bg_file_path=bg_match[1],
                            audio_format=config.tts_format
                        )
            
            if has_8d and getattr(config, "enable_8d_audio", True):
                audio_bytes, mime_type = apply_8d_audio_effect(
                    audio_bytes=audio_bytes,
                    audio_format=config.tts_format
                )

            chunk_id = f"chunk_{uuid.uuid4().hex[:12]}"
            item_meta = {
                "id": chunk_id,
                "user": user,
                "text": chunk.text,
                "voice": voice_used,
                "is_soundboard": chunk.is_soundboard,
                "is_death_counter": is_death_counter,
                "sound_name": chunk.sound_name,
                "has_fart_bg": has_fart_bg,
                "fart_bg_url": "/api/soundboard/fartbackground" if has_fart_bg else None,
                "has_8d": has_8d,
                "channel": clean_chan,
                "chunk_index": chunk.chunk_index + 1,
                "total_chunks": chunk.total_chunks,
                "url": f"/api/audio/{chunk_id}",
                "mime_type": mime_type,
                "created_at": time.time()
            }
            
            # Store audio bytes in memory store
            audio_store[chunk_id] = (audio_bytes, mime_type, item_meta)
            emit_chunk(item_meta)
            
        except Exception as e:
            logger.error(f"Failed to synthesize chunk '{chunk.text}': {e}")
            broadcast_event("error", {"message": "TTS synthesis failed for a message chunk."})


def on_twitch_message(user: str, message: str, channel: str = ""):
    """Callback triggered by Twitch IRC listener."""
    clean_chan = channel.strip().lstrip('#').lower() if channel else (config.channels[0] if config.channels else "")
    broadcast_event("chat_message", {"user": user, "message": message, "channel": clean_chan, "timestamp": time.time()})
    process_incoming_text(user=user, raw_text=message, channel=clean_chan)


class TTSRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Quiet standard HTTP logs to avoid spam
        pass

    def version_string(self):
        """Override to suppress server version fingerprinting (OWASP A05:2021)."""
        return "TwitchTTS"

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin:
            port = str(config.server_port)
            allowed = {
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            }
            if config.server_host not in ("0.0.0.0", "::", ""):
                allowed.add(f"http://{config.server_host}:{port}")
            if origin in allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")

    def _send_security_headers(self):
        """Send HTTP security headers for defense-in-depth on internet-exposed endpoints."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; media-src 'self' blob: data:; connect-src 'self' ws: wss:; img-src 'self' data: blob:; object-src 'none'; frame-ancestors 'self';")

    def _is_secure_request(self) -> bool:
        """Check if request is secure via config site_domain or HTTPS header."""
        if getattr(config, "site_domain", ""):
            return True
        if hasattr(self, "headers") and self.headers:
            proto = self.headers.get("X-Forwarded-Proto", "").lower()
            scheme = self.headers.get("X-Forwarded-Scheme", "").lower()
            if proto == "https" or scheme == "https":
                return True
        return False

    def _get_client_ip(self) -> str:
        """Get client IP address for rate limiting."""
        return self.client_address[0] if self.client_address else "unknown"

    def _get_request_auth_token(self) -> str:
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            for part in cookie_header.split(";"):
                k, _, v = part.strip().partition("=")
                if k.strip() == "session" and v.strip():
                    return v.strip()
        token = self.headers.get("X-Admin-Token")
        if not token:
            token = self.headers.get("Authorization", "")
            if token.startswith("Bearer "):
                token = token[7:]
        return token.strip() if token else ""

    def _check_auth(self, required_role: str = "admin") -> bool:
        token = self._get_request_auth_token()
        if not dashboard_auth_manager.verify_session(token, required_role=required_role):
            self._send_json(401, {
                "error": f"Unauthorized: {required_role.capitalize()} authentication required",
                "auth_required": dashboard_auth_manager.is_auth_required(),
                "admin_auth_required": dashboard_auth_manager.is_admin_auth_required(),
                "user_auth_required": dashboard_auth_manager.is_user_auth_required()
            })
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Route: SSE Event Stream (auth-gated on admin server — OWASP API2:2023)
        if path == "/api/events":
            # Require authentication when passwords are configured
            if dashboard_auth_manager.is_auth_required():
                token = self._get_request_auth_token()
                if not dashboard_auth_manager.verify_session(token, required_role="user"):
                    self._send_json(401, {
                        "error": "Unauthorized: Authentication required for event stream",
                        "auth_required": True
                    })
                    return

            handle_sse_stream(self, is_admin=True)
            return

        # Route: Stream Audio File
        if path.startswith("/api/audio/"):
            raw_id = path.split("/api/audio/")[-1]
            chunk_id = sanitize_identifier(raw_id, max_len=64)
            if chunk_id and chunk_id in audio_store:
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
            role = dashboard_auth_manager.get_session_role(tok)
            authenticated = dashboard_auth_manager.verify_session(tok, required_role="user")
            self._send_json(200, {
                "auth_required": dashboard_auth_manager.is_auth_required(),
                "admin_auth_required": dashboard_auth_manager.is_admin_auth_required(),
                "user_auth_required": dashboard_auth_manager.is_user_auth_required(),
                "authenticated": authenticated,
                "role": role or ("admin" if not dashboard_auth_manager.is_auth_required() else None),
                "twitch_auth": twitch_bot.get_auth_info() if twitch_bot else {}
            })
            return

        # Route: API Status
        if path == "/api/status":
            self._send_json(200, self._get_status_dict())
            return

        # Route: Control Settings (per-channel)
        if path == "/api/control/settings":
            req_chan = query.get("channel", [""])[0] or query.get("ch", [""])[0]
            self._send_json(200, {"success": True, "channel": req_chan, "config": config.get_channel_settings(req_chan)})
            return

        # Route: User Voices List
        if path == "/api/user_voices":
            self._send_json(200, {"user_voices": user_voice_manager.get_all()})
            return

        # Route: Commands Catalog List
        if path == "/api/commands":
            self._send_json(200, {"commands": get_commands_catalog()})
            return

        # Route: TTS API Voices List Proxy
        if path in ("/api/voices", "/api/v1/voices"):
            try:
                voices_data = tts_client.get_voices()
                self._send_json(200, voices_data)
            except Exception as e:
                presets = [p.strip() for p in (getattr(config, "voice_presets", "") or "mieto, terapisti, terry, tuomo4, niilo").split(",") if p.strip()]
                self._send_json(200, {"voices": presets, "fallback": True})
            return


        # Route: Soundboard List
        if path == "/api/soundboard":
            sounds = soundboard_manager.get_available_sounds()
            self._send_json(200, {
                "enabled": config.enable_soundboard,
                "sounds": list(sounds.keys()),
            })
            return

        # Route: Stream Soundboard Raw Audio File
        if path.startswith("/api/soundboard/"):
            raw_sound_name = path.split("/api/soundboard/", 1)[-1]
            clean_name = urllib.parse.unquote(raw_sound_name).strip()
            base_name = os.path.splitext(clean_name)[0] if "." in clean_name else clean_name
            match = soundboard_manager.find_sound(clean_name) or soundboard_manager.find_sound(base_name)
            if match and os.path.exists(match[1]):
                file_path = match[1]
                mime_type = soundboard_manager.get_mime_type(file_path)
                try:
                    with open(file_path, "rb") as f:
                        audio_bytes = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Content-Length", str(len(audio_bytes)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(audio_bytes)
                    return
                except Exception as e:
                    logger.error(f"Error serving soundboard file '{file_path}': {e}")
                    self.send_error(500, "Error reading soundboard file")
                    return
            else:
                self.send_error(404, "Sound effect not found")
                return

        # Route: Pieruta Targets List
        if path == "/api/pieruta":
            self._send_json(200, {"pieruta_targets": list(pieruta_targets.keys())})
            return

        # Route: Kill Counter Status
        if path == "/api/counter":
            self._send_json(200, kill_counter_monitor.get_status_dict())
            return

        # Route: Proxy GET /api/tts
        if path == "/api/tts":
            if not tts_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            raw_text = query.get("text", [""])[0]
            raw_voice = query.get("voice", [None])[0]
            raw_model = query.get("model", [None])[0]
            raw_fmt = query.get("format", [None])[0]

            text = sanitize_string(raw_text, max_len=2000)
            voice = sanitize_identifier(raw_voice, max_len=100) if raw_voice is not None else None
            model = sanitize_identifier(raw_model, max_len=100) if raw_model is not None else None
            fmt = sanitize_audio_format(raw_fmt) if raw_fmt is not None else None
            
            has_8d_api = False
            if text and re.search(r'\{\s*8d\s*\}', text, re.IGNORECASE):
                has_8d_api = True
                text = re.sub(r'\{\s*8d\s*\}', '', text, flags=re.IGNORECASE).strip()

            if not text:
                self._send_json(400, {"error": "Missing required parameter 'text'"})
                return
                
            try:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=text, voice=voice, model=model, audio_format=fmt, method="GET"
                )
                if has_8d_api and getattr(config, "enable_8d_audio", True):
                    audio_bytes, mime_type = apply_8d_audio_effect(audio_bytes, audio_format=fmt or config.tts_format)
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(audio_bytes)
            except Exception as e:
                logger.error(f"GET /api/tts error: {e}")
                self._send_json(500, {"error": "TTS synthesis failed"})
            return

        # Serve static files (HTML, CSS, JS)
        if path in ("/", "/index.html"):
            file_path = os.path.join(STATIC_DIR, "index.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return

        if path in ("/control", "/control.html", "/user", "/user.html"):
            file_path = os.path.join(STATIC_DIR, "control.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return

        if path in ("/player", "/player.html", "/listen", "/listen.html"):
            file_path = os.path.join(STATIC_DIR, "player.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return

        if path in ("/obs", "/obs.html", "/overlay", "/overlay.html"):
            file_path = os.path.join(STATIC_DIR, "obs.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return

        if path in ("/viewer", "/viewer.html", "/commands", "/commands.html"):
            file_path = os.path.join(STATIC_DIR, "viewer.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return


        if path == "/darkcounter_obs.lua":
            serve_darkcounter_lua(self, query)
            return
            
        rel_path = path.lstrip('/')
        safe_path = os.path.abspath(os.path.join(STATIC_DIR, rel_path))
        static_dir_abs = os.path.abspath(STATIC_DIR)
        if os.path.isfile(safe_path) and (os.path.commonpath([static_dir_abs, safe_path]) == static_dir_abs):
            if path.endswith(".html"):
                mime = "text/html; charset=utf-8"
            elif path.endswith(".css"):
                mime = "text/css"
            elif path.endswith(".js"):
                mime = "application/javascript"
            elif path.endswith(".svg"):
                mime = "image/svg+xml"
            elif path.endswith(".png"):
                mime = "image/png"
            elif path.endswith(".json"):
                mime = "application/json"
            else:
                mime = "text/plain"
            self._serve_static_file(safe_path, mime)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            content_len = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_len = 0

        # Maximum payload limit (5MB)
        if content_len > 5 * 1024 * 1024:
            self._send_json(413, {"error": "Payload too large (max 5MB)"})
            return

        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(post_data.decode('utf-8')) if post_data else {}
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}

        # Route: Validate Twitch Token (Public/Auth tool)
        if path == "/api/auth/validate_twitch":
            if not validate_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            token = sanitize_string(body.get("oauth_token"), max_len=500)
            res = twitch_token_validator.validate_token(token)
            self._send_json(200, res)
            return


        # Route: Set Pieruta Target
        if path == "/api/pieruta":
            if not soundboard_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            raw_user = body.get("user") or body.get("username") or ""
            target_user = sanitize_identifier(raw_user.lstrip('@'), max_len=100) if raw_user else ""
            if not target_user:
                self._send_json(400, {"error": "Missing or invalid 'user' parameter"})
                return
            pieruta_targets[target_user.lower()] = True
            self._send_json(200, {"success": True, "target": target_user, "message": f"Fart background queued for @{target_user}'s next message"})
            return

        # Route: Remote / Local Kill Counter Update
        if path == "/api/counter":
            if not counter_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return

            req_token = self._get_request_auth_token()
            if config.kill_counter_api_token:
                if req_token != config.kill_counter_api_token and not dashboard_auth_manager.verify_session(req_token):
                    self._send_json(401, {"error": "Unauthorized: Invalid counter API token", "auth_required": True})
                    return
            elif dashboard_auth_manager.is_auth_required():
                if not self._check_auth():
                    return

            channel = sanitize_identifier(body.get("channel", ""), max_len=100) if body.get("channel") else ""

            if "increment" in body or "delta" in body:
                amt = sanitize_int(body.get("increment", body.get("delta", 1)), default=1, min_val=-1000, max_val=1000)
                res = kill_counter_monitor.increment(amt, channel=channel)
                self._send_json(200, res)
                return
            if "count" in body or "set" in body:
                cnt = sanitize_int(body.get("count", body.get("set", 0)), default=0, min_val=0, max_val=1000000)
                trigger = sanitize_bool(body.get("trigger_tts", False), default=False)
                res = kill_counter_monitor.set_count(cnt, trigger_tts=trigger, channel=channel)
                self._send_json(200, res)
                return
            verse = kill_counter_monitor.trigger_bible_tts(channel=channel)
            self._send_json(200, {"success": True, "count": kill_counter_monitor.current_count, "verse": verse})
            return

        # Route: Test Bible TTS Trigger
        if path == "/api/counter/test":
            if not counter_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return

            req_token = self._get_request_auth_token()
            if config.kill_counter_api_token:
                if req_token != config.kill_counter_api_token and not dashboard_auth_manager.verify_session(req_token):
                    self._send_json(401, {"error": "Unauthorized: Invalid counter API token", "auth_required": True})
                    return
            elif dashboard_auth_manager.is_auth_required():
                if not self._check_auth():
                    return

            channel = sanitize_identifier(body.get("channel", ""), max_len=100) if body.get("channel") else ""
            verse = kill_counter_monitor.trigger_bible_tts(channel=channel)
            self._send_json(200, {"success": True, "count": kill_counter_monitor.current_count, "verse": verse})
            return

        # Route: Admin / User Login
        if path == "/api/auth/login":
            if not login_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Too many login attempts. Try again later."})
                return
            password = sanitize_string(body.get("password"), max_len=500)
            success, session_token, err, role = dashboard_auth_manager.authenticate(password)
            if success:
                secure_flag = "; Secure" if self._is_secure_request() else ""
                cookie_str = f"session={session_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400{secure_flag}"
                self._send_json(200, {"success": True, "token": session_token, "role": role}, cookies=[cookie_str])
            else:
                self._send_json(401, {"error": err or "Invalid password"})
            return

        # Route: Admin / User Logout
        if path == "/api/auth/logout":
            tok = self._get_request_auth_token()
            dashboard_auth_manager.revoke_session(tok)
            secure_flag = "; Secure" if self._is_secure_request() else ""
            cookie_str = f"session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure_flag}"
            self._send_json(200, {"success": True}, cookies=[cookie_str])
            return

        # Route: Proxy POST /api/tts
        if path == "/api/tts":
            if not tts_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            text = sanitize_string(body.get("text"), max_len=2000)
            voice = sanitize_identifier(body.get("voice"), max_len=100) if body.get("voice") is not None else None
            model = sanitize_identifier(body.get("model"), max_len=100) if body.get("model") is not None else None
            fmt = sanitize_audio_format(body.get("format")) if body.get("format") is not None else None
            
            has_8d_api = False
            if text and re.search(r'\{\s*8d\s*\}', text, re.IGNORECASE):
                has_8d_api = True
                text = re.sub(r'\{\s*8d\s*\}', '', text, flags=re.IGNORECASE).strip()

            if not text:
                self._send_json(400, {"error": "Missing required field 'text'"})
                return
                
            try:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=text, voice=voice, model=model, audio_format=fmt, method="POST"
                )
                if has_8d_api and getattr(config, "enable_8d_audio", True):
                    audio_bytes, mime_type = apply_8d_audio_effect(audio_bytes, audio_format=fmt or config.tts_format)
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
                logger.error(f"POST /api/tts error: {e}")
                self._send_json(500, {"error": "TTS synthesis failed"})
            return

        # Route: Upload New Soundboard Effect (Strict sanitization + Streamer name password check)
        if path == "/api/soundboard/upload":
            if not soundboard_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Upload rate limit exceeded. Please wait a minute before uploading another sound."})
                return
            if not config.enable_soundboard:
                self._send_json(400, {"error": "Soundboard is currently disabled."})
                return

            file_bytes, filename, custom_sound_name, password = extract_upload_payload(self.headers, post_data, body)

            active_chans = list(twitch_bot.channels) if twitch_bot and twitch_bot.channels else ([config.twitch_channel] if config.twitch_channel else [])
            if not verify_streamer_password(password, active_chans):
                self._send_json(401, {
                    "error": "Unauthorized: Streamer Password must match an active connected Twitch channel name (e.g. shroud)."
                })
                return

            try:
                clean_sound_name, clean_filename = validate_and_sanitize_audio_upload(
                    file_bytes=file_bytes,
                    filename=filename,
                    custom_sound_name=custom_sound_name
                )
            except ValueError as ve:
                self._send_json(400, {"error": str(ve)})
                return

            saved_name, file_path = soundboard_manager.save_uploaded_sound(
                clean_sound_name=clean_sound_name,
                clean_filename=clean_filename,
                file_bytes=file_bytes
            )

            broadcast_event("soundboard_updated", {
                "action": "upload",
                "sound_name": saved_name,
                "sounds": list(soundboard_manager.get_available_sounds().keys())
            })

            self._send_json(200, {
                "success": True,
                "message": f"Soundboard effect '({saved_name})' uploaded successfully!",
                "sound_name": saved_name,
                "audio_url": f"/api/soundboard/{saved_name}"
            })
            return


        # Check user/streamer authentication for control portal routes
        if not self._check_auth(required_role="user"):
            return

        # Route: Trigger Soundboard Effect (User role required when auth enabled)
        if path in ("/api/soundboard/trigger", "/api/soundboard/play"):
            if not soundboard_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            if not config.enable_soundboard:
                self._send_json(400, {"error": "Soundboard is currently disabled"})
                return
            raw_sound = body.get("sound") or body.get("sound_name") or body.get("name") or ""
            clean_sound = sanitize_identifier(raw_sound, max_len=100)
            if not clean_sound:
                self._send_json(400, {"error": "Missing or invalid 'sound' parameter"})
                return
            sound_match = soundboard_manager.find_sound(clean_sound)
            if not sound_match:
                self._send_json(404, {"error": f"Soundboard effect '{clean_sound}' not found"})
                return
            matched_name, file_path = sound_match
            req_chan = sanitize_string(body.get("channel") or config.twitch_channel, max_len=100)
            user = sanitize_string(body.get("user", "Control Portal"), max_len=50, default="Control Portal")
            
            # Broadcast soundboard play event via SSE
            sb_chunk = {
                "id": f"sb_{int(time.time()*1000)}",
                "url": f"/api/soundboard/{matched_name}",
                "speaker": user,
                "text": f"({matched_name})",
                "voice": "Soundboard",
                "channel": req_chan,
                "timestamp": time.time(),
                "is_soundboard": True
            }
            broadcast_event("audio_chunk", sb_chunk)
            broadcast_event("soundboard_trigger", {
                "sound_name": matched_name,
                "file_path": f"/api/soundboard/{matched_name}",
                "user": user,
                "channel": req_chan,
                "timestamp": time.time()
            })
            self._send_json(200, {
                "success": True,
                "sound_name": matched_name,
                "audio_url": f"/api/soundboard/{matched_name}",
                "channel": req_chan
            })
            return


        # Route: Toggle Soundboard
        if path == "/api/soundboard/toggle":
            if "enabled" in body:
                config.enable_soundboard = sanitize_bool(body["enabled"], default=config.enable_soundboard)
            else:
                config.enable_soundboard = not config.enable_soundboard
            config.save()
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "enabled": config.enable_soundboard})
            return

        # Route: Save user/control settings
        if path == "/api/control/settings":
            target_chan = sanitize_string(body.get("channel") or body.get("twitch_channel") or "", max_len=100)
            settings_to_update = {}
            if "enable_8d_audio" in body:
                settings_to_update["enable_8d_audio"] = sanitize_bool(body["enable_8d_audio"], default=config.enable_8d_audio)
            if "effect_8d_speed" in body:
                settings_to_update["effect_8d_speed"] = sanitize_float(body["effect_8d_speed"], default=config.effect_8d_speed, min_val=0.01, max_val=5.0)
            if "same_user_timeout" in body:
                settings_to_update["same_user_timeout"] = sanitize_float(body["same_user_timeout"], default=config.same_user_timeout, min_val=0.0, max_val=300.0)
            if "enable_chat_responses" in body:
                settings_to_update["enable_chat_responses"] = sanitize_bool(body["enable_chat_responses"], default=config.enable_chat_responses)
            if "enable_kill_counter" in body:
                settings_to_update["enable_kill_counter"] = sanitize_bool(body["enable_kill_counter"], default=config.enable_kill_counter)
            if "enable_chaos_mode" in body or "chaos_mode" in body:
                raw_chaos = body.get("enable_chaos_mode", body.get("chaos_mode"))
                settings_to_update["enable_chaos_mode"] = sanitize_bool(raw_chaos, default=config.enable_chaos_mode)

            config.set_channel_settings(target_chan, settings_to_update)
            config.save()
            broadcast_event("status", self._get_status_dict())
            eff_cfg = config.get_channel_settings(target_chan)
            broadcast_event("chaos_mode_update", {"chaos_mode": eff_cfg.get("enable_chaos_mode"), "channel": target_chan})
            self._send_json(200, {"success": True, "channel": target_chan, "config": eff_cfg})
            return

        # Route: Toggle Chaos Mode directly
        if path in ("/api/chaos", "/api/chaos/toggle"):
            target_chan = sanitize_string(body.get("channel") or "", max_len=100)
            chan_cfg = config.get_channel_settings(target_chan)
            curr_chaos = chan_cfg.get("enable_chaos_mode", config.enable_chaos_mode)
            if "enabled" in body:
                new_chaos = sanitize_bool(body["enabled"], default=curr_chaos)
            elif "enable_chaos_mode" in body:
                new_chaos = sanitize_bool(body["enable_chaos_mode"], default=curr_chaos)
            else:
                new_chaos = not curr_chaos
            config.set_channel_settings(target_chan, {"enable_chaos_mode": new_chaos})
            config.save()
            broadcast_event("status", self._get_status_dict())
            broadcast_event("chaos_mode_update", {"chaos_mode": new_chaos, "channel": target_chan})
            self._send_json(200, {"success": True, "channel": target_chan, "chaos_mode": new_chaos})
            return

        # Route: Connect Twitch Channel
        if path == "/api/connect":
            raw_chan = body.get("channel")
            sanitized = sanitize_channels_list(raw_chan)
            if not sanitized:
                self._send_json(400, {"error": "Valid Twitch channel name(s) required (up to 2 alphanumeric/underscore channels)"})
                return
            config.twitch_channel = sanitized
            config.save()
            if twitch_bot:
                twitch_bot.set_channel(sanitized)
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "channel": config.twitch_channel, "channels": config.channels})
            return

        # Route: Skip Current Audio Track
        if path in ("/api/queue/skip", "/api/skip"):
            user = sanitize_string(body.get("user", "Dashboard"), max_len=50, default="Dashboard")
            broadcast_event("skip_audio", {"user": user, "channel": config.twitch_channel, "timestamp": time.time()})
            skip_msg = f"⏭️ Audio skipped by {user}."
            broadcast_event("chat_message", {"user": "System", "message": skip_msg, "channel": config.twitch_channel, "timestamp": time.time()})
            self._send_json(200, {"success": True, "message": "Audio skip triggered."})
            return

        # Route: Clear Audio Queue
        if path == "/api/queue/clear":
            audio_queue.clear()
            broadcast_event("clear_audio", {"user": "Dashboard", "timestamp": time.time()})
            self._send_json(200, {"success": True, "message": "Audio queue cleared."})
            return

        # Route: Manual Test TTS
        if path == "/api/tts/test":
            text = sanitize_string(body.get("text"), max_len=2000)
            voice = sanitize_identifier(body.get("voice"), max_len=100) if body.get("voice") is not None else None
            model = sanitize_identifier(body.get("model"), max_len=100) if body.get("model") is not None else None
            user = sanitize_string(body.get("user", "TestUser"), max_len=50, default="TestUser")
            req_chan = sanitize_string(body.get("channel"), max_len=100) if body.get("channel") else ""
            
            if not text:
                self._send_json(400, {"error": "Text is required"})
                return
                
            threading.Thread(
                target=process_incoming_text,
                kwargs={"user": user, "raw_text": text, "override_voice": voice, "override_model": model, "channel": req_chan},
                daemon=True
            ).start()
            
            self._send_json(200, {"success": True, "message": "Test TTS job queued.", "channel": req_chan})
            return


        # Route: User Voices Management
        if path == "/api/user_voices/set":
            username = sanitize_username(body.get("user"))
            voice = sanitize_identifier(body.get("voice"), max_len=100)
            locked = bool(body.get("locked", False))
            if not username or not voice:
                self._send_json(400, {"error": "Both valid 'user' and 'voice' parameters are required"})
                return
            saved = user_voice_manager.set_voice(username, voice, locked=locked, force=True)
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "user": username, "voice": saved, "user_voices": user_voice_manager.get_all()})
            return

        if path == "/api/user_voices/delete":
            username = sanitize_username(body.get("user"))
            if not username:
                self._send_json(400, {"error": "Valid parameter 'user' is required"})
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

        # Protected administrative routes below (requires admin role)
        if not self._check_auth(required_role="admin"):
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

        # Route: Save Config/Settings
        if path == "/api/settings":
            if "tts_api_url" in body:
                config.tts_api_url = sanitize_tts_url(body["tts_api_url"], default=config.tts_api_url)
                tts_client.base_url = config.tts_api_url.rstrip('/')
            if "tts_voice" in body:
                config.tts_voice = sanitize_identifier(body["tts_voice"], max_len=100, default=config.tts_voice)
            if "tts_model" in body:
                config.tts_model = sanitize_identifier(body["tts_model"], max_len=100, default=config.tts_model)
            if "tts_format" in body:
                config.tts_format = sanitize_audio_format(body["tts_format"], default=config.tts_format)
            if "tts_language" in body:
                config.tts_language = sanitize_string(body["tts_language"], max_len=20, default=config.tts_language)
            if "tts_speed" in body:
                config.tts_speed = sanitize_float(body["tts_speed"], default=config.tts_speed, min_val=0.1, max_val=10.0)
            if "tts_num_step" in body:
                config.tts_num_step = sanitize_int(body["tts_num_step"], default=config.tts_num_step, min_val=1, max_val=500)
            if "tts_guidance_scale" in body:
                config.tts_guidance_scale = sanitize_float(body["tts_guidance_scale"], default=config.tts_guidance_scale, min_val=0.0, max_val=50.0)
            if "tts_seed" in body:
                config.tts_seed = sanitize_int(body["tts_seed"], default=config.tts_seed, min_val=-1, max_val=2147483647)
            if "user_template" in body:
                config.user_template = sanitize_string(body["user_template"], max_len=500, default=config.user_template)
            if "voice_presets" in body:
                config.voice_presets = sanitize_string(body["voice_presets"], max_len=1000, default=config.voice_presets)
            if "shouting_voices" in body:
                config.shouting_voices = sanitize_string(body["shouting_voices"], max_len=1000, default=config.shouting_voices)
            elif "shoutingvoices" in body:
                config.shouting_voices = sanitize_string(body["shoutingvoices"], max_len=1000, default=config.shouting_voices)
            if "effect_8d_speed" in body:
                config.effect_8d_speed = sanitize_float(body["effect_8d_speed"], default=config.effect_8d_speed, min_val=0.01, max_val=5.0)
            elif "eight_d_speed" in body:
                config.effect_8d_speed = sanitize_float(body["eight_d_speed"], default=config.effect_8d_speed, min_val=0.01, max_val=5.0)
            elif "8d_speed" in body:
                config.effect_8d_speed = sanitize_float(body["8d_speed"], default=config.effect_8d_speed, min_val=0.01, max_val=5.0)
            if "twitch_bot_username" in body:
                cleaned_bot_user = sanitize_username(body["twitch_bot_username"])
                if cleaned_bot_user:
                    config.twitch_bot_username = cleaned_bot_user
            if "twitch_oauth_token" in body:
                raw_tok = sanitize_string(body["twitch_oauth_token"], max_len=500)
                # Don't update if sent masked string unless it changed
                if raw_tok and not raw_tok.startswith("oauth:••••") and not raw_tok.startswith("••••"):
                    config.twitch_oauth_token = raw_tok
            if "enable_chat_responses" in body:
                config.enable_chat_responses = sanitize_bool(body["enable_chat_responses"], default=config.enable_chat_responses)
            if "enable_periodic_info" in body:
                config.enable_periodic_info = sanitize_bool(body["enable_periodic_info"], default=config.enable_periodic_info)
            if "periodic_info_interval" in body:
                config.periodic_info_interval = sanitize_int(body["periodic_info_interval"], default=config.periodic_info_interval, min_val=1, max_val=1440)
            if "admin_password" in body:
                raw_pwd = sanitize_string(body["admin_password"], max_len=500)
                if raw_pwd and raw_pwd != "••••••••":
                    config.admin_password = hash_password(raw_pwd)
            if "user_password" in body:
                raw_upwd = sanitize_string(body["user_password"], max_len=500)
                if raw_upwd and raw_upwd != "••••••••":
                    config.user_password = hash_password(raw_upwd)
                elif raw_upwd == "":
                    config.user_password = ""
            if "twitch_client_id" in body:
                config.twitch_client_id = sanitize_string(body["twitch_client_id"], max_len=200)
            if "same_user_timeout" in body:
                config.same_user_timeout = sanitize_float(body["same_user_timeout"], default=config.same_user_timeout, min_val=0.0, max_val=300.0)
            if "enable_kill_counter" in body:
                config.enable_kill_counter = sanitize_bool(body["enable_kill_counter"], default=config.enable_kill_counter)
            if "kill_counter_file" in body:
                candidate = sanitize_string(body["kill_counter_file"], max_len=500, default=config.kill_counter_file)
                if candidate:
                    base_abs = os.path.abspath(BASE_DIR)
                    resolved = os.path.abspath(os.path.join(base_abs, candidate))
                    if resolved == base_abs or resolved.startswith(base_abs + os.sep):
                        config.kill_counter_file = candidate
            if "kill_counter_poll_interval" in body:
                config.kill_counter_poll_interval = sanitize_float(body["kill_counter_poll_interval"], default=config.kill_counter_poll_interval, min_val=0.1, max_val=60.0)
            if "kill_counter_voice" in body:
                config.kill_counter_voice = sanitize_identifier(body["kill_counter_voice"], max_len=100, default=config.kill_counter_voice)
            if "kill_counter_template" in body:
                config.kill_counter_template = sanitize_string(body["kill_counter_template"], max_len=500, default=config.kill_counter_template)
            if "bible_api_url" in body:
                config.bible_api_url = sanitize_url(body["bible_api_url"], default=config.bible_api_url)
            if "kill_counter_api_token" in body:
                raw_ctok = sanitize_string(body["kill_counter_api_token"], max_len=500)
                if raw_ctok and not raw_ctok.startswith("••••"):
                    config.kill_counter_api_token = raw_ctok
                elif raw_ctok == "":
                    config.kill_counter_api_token = ""
            
            config.save()
            dashboard_auth_manager.update_passwords(config.admin_password, config.user_password)
            if twitch_bot:
                twitch_bot.set_credentials(config.twitch_bot_username, config.twitch_oauth_token)
            
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "config": self._get_config_dict()})
            return

        # Route: User Voices Management
        if path == "/api/user_voices/set":
            username = sanitize_username(body.get("user"))
            voice = sanitize_identifier(body.get("voice"), max_len=100)
            locked = bool(body.get("locked", False))
            if not username or not voice:
                self._send_json(400, {"error": "Both valid 'user' and 'voice' parameters are required"})
                return
            saved = user_voice_manager.set_voice(username, voice, locked=locked, force=True)
            broadcast_event("status", self._get_status_dict())
            self._send_json(200, {"success": True, "user": username, "voice": saved, "user_voices": user_voice_manager.get_all()})
            return

        if path == "/api/user_voices/delete":
            username = sanitize_username(body.get("user"))
            if not username:
                self._send_json(400, {"error": "Valid parameter 'user' is required"})
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
        """Status dict for admin server — uses masked config (never raw to_dict)."""
        return {
            "channel": config.twitch_channel,
            "channels": config.channels,
            "connected": bool(twitch_bot and twitch_bot.running and (twitch_bot.channels or twitch_bot.channel)),
            "authenticated": bool(twitch_bot and twitch_bot.is_authenticated),
            "config": self._get_config_dict(),
            "user_voices": user_voice_manager.get_all(),
            "auth_required": dashboard_auth_manager.is_auth_required(),
            "twitch_auth": twitch_bot.get_auth_info() if twitch_bot else {},
            "bot_status": twitch_bot.get_status() if twitch_bot else {},
            "counter": kill_counter_monitor.get_status_dict()
        }

    def _get_config_dict(self) -> dict:
        return config.to_masked_dict()

    def _send_json(self, code: int, data: dict, cookies: list = None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookies:
            for c in cookies:
                self.send_header("Set-Cookie", c)
        self._send_cors_headers()
        self._send_security_headers()
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
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error reading static file {filepath}: {e}")
            self.send_error(500, "Internal server error")
            
class PublicRequestHandler(BaseHTTPRequestHandler):
    """
    Unified internet-facing HTTP handler for public pages:
      /              → Streamer Control Portal (password-protected)
      /control       → Streamer Control Portal (password-protected)
      /player        → Voice Player (public, read-only)
      /obs           → OBS Browser Source Overlay (public, read-only)

    Security:
    - Whitelists only safe API routes; admin-only routes (/api/settings, /api/bot/*) are blocked.
    - Enforces authentication on mutating control-portal routes.
    - Player and OBS overlay are read-only and safe without authentication.
    - Serves only whitelisted static assets (no index.html / admin dashboard).
    - Adds defense-in-depth security headers to every response.
    """

    # Whitelisted static files that may be served on the public server
    _ALLOWED_STATIC_FILES = {
        "control.html", "control.css", "control.js",
        "player.html", "player.css", "player.js",
        "obs.html", "obs.css", "obs.js",
        "viewer.html", "viewer.css", "viewer.js",
        "darkcounter_obs.lua",
    }


    def log_message(self, format, *args):
        pass

    def version_string(self):
        """Override to suppress server version fingerprinting (OWASP A05:2021)."""
        return "TwitchTTS"

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin:
            public_port = str(config.public_server_port)
            allowed = {
                f"http://localhost:{public_port}",
                f"http://127.0.0.1:{public_port}",
            }
            if config.public_server_host not in ("0.0.0.0", "::", ""):
                allowed.add(f"http://{config.public_server_host}:{public_port}")
            if origin in allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")

    def _send_security_headers(self, allow_framing: bool = False):
        """Send HTTP security headers. allow_framing=True for OBS overlay pages."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        frame_policy = "*" if allow_framing else "'self'"
        self.send_header("Content-Security-Policy", f"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; media-src 'self' blob: data:; connect-src 'self' ws: wss:; img-src 'self' data: blob:; object-src 'none'; frame-ancestors {frame_policy};")
        if allow_framing:
            self.send_header("X-Frame-Options", "ALLOWALL")
        else:
            self.send_header("X-Frame-Options", "SAMEORIGIN")

    def _is_secure_request(self) -> bool:
        """Check if request is secure via config site_domain or HTTPS header."""
        if getattr(config, "site_domain", ""):
            return True
        if hasattr(self, "headers") and self.headers:
            proto = self.headers.get("X-Forwarded-Proto", "").lower()
            scheme = self.headers.get("X-Forwarded-Scheme", "").lower()
            if proto == "https" or scheme == "https":
                return True
        return False

    def _get_client_ip(self) -> str:
        return self.client_address[0] if self.client_address else "unknown"

    def _get_request_auth_token(self) -> str:
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            for part in cookie_header.split(";"):
                k, _, v = part.strip().partition("=")
                if k.strip() == "session" and v.strip():
                    return v.strip()
        token = self.headers.get("X-Admin-Token")
        if not token:
            token = self.headers.get("Authorization", "")
            if token.startswith("Bearer "):
                token = token[7:]
        return token.strip() if token else ""

    def _check_auth(self, required_role: str = "user") -> bool:
        token = self._get_request_auth_token()
        if not dashboard_auth_manager.verify_session(token, required_role=required_role):
            self._send_json(401, {
                "error": f"Unauthorized: {required_role.capitalize()} authentication required",
                "auth_required": dashboard_auth_manager.is_auth_required(),
                "admin_auth_required": dashboard_auth_manager.is_admin_auth_required(),
                "user_auth_required": dashboard_auth_manager.is_user_auth_required()
            })
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # ── SSE Event Stream (public — with connection limits) ──
        if path == "/api/events":
            handle_sse_stream(self, is_admin=False)
            return

        # ── Audio Chunk Streaming ──
        if path.startswith("/api/audio/"):
            raw_id = path.split("/api/audio/")[-1]
            chunk_id = sanitize_identifier(raw_id, max_len=64)
            if chunk_id and chunk_id in audio_store:
                audio_bytes, mime_type, _ = audio_store[chunk_id]
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self._send_cors_headers()
                self._send_security_headers(allow_framing=True)
                self.end_headers()
                self.wfile.write(audio_bytes)
                return
            else:
                self.send_error(404, "Audio chunk not found")
                return

        # ── Soundboard Audio File Streaming ──
        if path.startswith("/api/soundboard/"):
            raw_sound_name = path.split("/api/soundboard/", 1)[-1]
            clean_name = urllib.parse.unquote(raw_sound_name).strip()
            base_name = os.path.splitext(clean_name)[0] if "." in clean_name else clean_name
            match = soundboard_manager.find_sound(clean_name) or soundboard_manager.find_sound(base_name)
            if match and os.path.exists(match[1]):
                file_path = match[1]
                mime_type = soundboard_manager.get_mime_type(file_path)
                try:
                    with open(file_path, "rb") as f:
                        audio_bytes = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Content-Length", str(len(audio_bytes)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self._send_cors_headers()
                    self._send_security_headers(allow_framing=True)
                    self.end_headers()
                    self.wfile.write(audio_bytes)
                    return
                except Exception as e:
                    logger.error(f"Error serving soundboard file '{file_path}' on public server: {e}")
                    self.send_error(500, "Error reading soundboard file")
                    return
            else:
                self.send_error(404, "Sound effect not found")
                return

        # ── Auth Status (public — no twitch_auth metadata) ──
        if path == "/api/auth/status":
            tok = self._get_request_auth_token()
            role = dashboard_auth_manager.get_session_role(tok)
            authenticated = dashboard_auth_manager.verify_session(tok, required_role="user")
            self._send_json(200, {
                "auth_required": dashboard_auth_manager.is_auth_required(),
                "admin_auth_required": dashboard_auth_manager.is_admin_auth_required(),
                "user_auth_required": dashboard_auth_manager.is_user_auth_required(),
                "authenticated": authenticated,
                "role": role or ("admin" if not dashboard_auth_manager.is_auth_required() else None),
            })
            return

        # ── API Status (sanitized, no admin creds) ──
        if path == "/api/status":
            self._send_json(200, self._get_public_status_dict())
            return

        # ── Control Settings (per-channel) ──
        if path == "/api/control/settings":
            req_chan = query.get("channel", [""])[0] or query.get("ch", [""])[0]
            self._send_json(200, {"success": True, "channel": req_chan, "config": config.get_channel_settings(req_chan)})
            return

        # ── User Voices List (public) ──
        if path == "/api/user_voices":
            self._send_json(200, {"user_voices": user_voice_manager.get_all()})
            return

        # ── Commands Catalog (public) ──
        if path == "/api/commands":
            self._send_json(200, {"commands": get_commands_catalog()})
            return

        # ── TTS Voices List Proxy (public) ──
        if path in ("/api/voices", "/api/v1/voices"):
            try:
                voices_data = tts_client.get_voices()
                self._send_json(200, voices_data)
            except Exception as e:
                presets = [p.strip() for p in (getattr(config, "voice_presets", "") or "mieto, terapisti, terry, tuomo4, niilo").split(",") if p.strip()]
                self._send_json(200, {"voices": presets, "fallback": True})
            return


        # ── Soundboard List (public — no filesystem paths) ──
        if path == "/api/soundboard":
            sounds = soundboard_manager.get_available_sounds()
            self._send_json(200, {
                "enabled": config.enable_soundboard,
                "sounds": list(sounds.keys()),
            })
            return

        # ── Pieruta Targets (public) ──
        if path == "/api/pieruta":
            self._send_json(200, {"pieruta_targets": list(pieruta_targets.keys())})
            return

        # ── Kill Counter Status (public) ──
        if path == "/api/counter":
            self._send_json(200, kill_counter_monitor.get_status_dict())
            return

        # ── Proxy GET /api/tts (public, rate-limited) ──
        if path == "/api/tts":
            if not tts_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            raw_text = query.get("text", [""])[0]
            raw_voice = query.get("voice", [None])[0]
            raw_model = query.get("model", [None])[0]
            raw_fmt = query.get("format", [None])[0]
            text = sanitize_string(raw_text, max_len=2000)
            voice = sanitize_identifier(raw_voice, max_len=100) if raw_voice is not None else None
            model = sanitize_identifier(raw_model, max_len=100) if raw_model is not None else None
            fmt = sanitize_audio_format(raw_fmt) if raw_fmt is not None else None

            has_8d_api = False
            if text and re.search(r'\{\s*8d\s*\}', text, re.IGNORECASE):
                has_8d_api = True
                text = re.sub(r'\{\s*8d\s*\}', '', text, flags=re.IGNORECASE).strip()

            if not text:
                self._send_json(400, {"error": "Missing required parameter 'text'"})
                return
            try:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=text, voice=voice, model=model, audio_format=fmt, method="GET"
                )
                if has_8d_api and getattr(config, "enable_8d_audio", True):
                    audio_bytes, mime_type = apply_8d_audio_effect(audio_bytes, audio_format=fmt or config.tts_format)
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(audio_bytes)
            except Exception as e:
                logger.error(f"GET /api/tts error on public server: {e}")
                self._send_json(500, {"error": "TTS synthesis failed"})
            return

        # ── Serve Public Static Pages ──
        # Control Portal (default landing page)
        if path in ("/", "/control", "/control.html", "/user", "/user.html"):
            file_path = os.path.join(STATIC_DIR, "control.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return

        # Voice Player
        if path in ("/player", "/player.html", "/listen", "/listen.html"):
            file_path = os.path.join(STATIC_DIR, "player.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return

        # OBS Overlay
        if path in ("/obs", "/obs.html", "/overlay", "/overlay.html"):
            file_path = os.path.join(STATIC_DIR, "obs.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8", allow_framing=True)
            return

        # Viewer Page
        if path in ("/viewer", "/viewer.html", "/commands", "/commands.html"):
            file_path = os.path.join(STATIC_DIR, "viewer.html")
            self._serve_static_file(file_path, "text/html; charset=utf-8")
            return


        # DarkCounter LUA Script Download
        if path == "/darkcounter_obs.lua":
            serve_darkcounter_lua(self, query)
            return

        # Serve whitelisted static assets (CSS, JS) for public pages only
        rel_path = path.lstrip('/')
        if rel_path in self._ALLOWED_STATIC_FILES:
            safe_path = os.path.abspath(os.path.join(STATIC_DIR, rel_path))
            static_dir_abs = os.path.abspath(STATIC_DIR)
            if os.path.isfile(safe_path) and (os.path.commonpath([static_dir_abs, safe_path]) == static_dir_abs):
                if rel_path.endswith(".css"):
                    mime = "text/css"
                elif rel_path.endswith(".js"):
                    mime = "application/javascript"
                else:
                    mime = "text/html; charset=utf-8"
                is_obs = rel_path.startswith("obs.")
                self._serve_static_file(safe_path, mime, allow_framing=is_obs)
                return

        # Block admin dashboard and all un-whitelisted routes
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # ── Block admin-only routes ──
        blocked_admin_routes = (
            "/api/settings",
            "/api/bot/reconnect",
            "/api/bot/send_info",
        )
        if path in blocked_admin_routes:
            self._send_json(403, {"error": "Forbidden: This route is not available on the public server"})
            return

        try:
            content_len = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_len = 0

        # Maximum payload limit (5MB)
        if content_len > 5 * 1024 * 1024:
            self._send_json(413, {"error": "Payload too large (max 5MB)"})
            return

        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            body = json.loads(post_data.decode('utf-8')) if post_data else {}
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}

        # ── Public POST routes (no auth required) ──

        # Validate Twitch Token
        if path == "/api/auth/validate_twitch":
            if not validate_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            token = sanitize_string(body.get("oauth_token"), max_len=500)
            res = twitch_token_validator.validate_token(token)
            self._send_json(200, res)
            return

        # Login
        if path == "/api/auth/login":
            if not login_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Too many login attempts. Try again later."})
                return
            password = sanitize_string(body.get("password"), max_len=500)
            success, session_token, err, role = dashboard_auth_manager.authenticate(password, max_role="user")
            if success:
                secure_flag = "; Secure" if self._is_secure_request() else ""
                cookie_str = f"session={session_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400{secure_flag}"
                self._send_json(200, {"success": True, "token": session_token, "role": role}, cookies=[cookie_str])
            else:
                self._send_json(401, {"error": err or "Invalid password"})
            return

        # Logout
        if path == "/api/auth/logout":
            tok = self._get_request_auth_token()
            dashboard_auth_manager.revoke_session(tok)
            secure_flag = "; Secure" if self._is_secure_request() else ""
            cookie_str = f"session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure_flag}"
            self._send_json(200, {"success": True}, cookies=[cookie_str])
            return


        # Set Pieruta Target
        if path == "/api/pieruta":
            if not soundboard_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            raw_user = body.get("user") or body.get("username") or ""
            target_user = sanitize_identifier(raw_user.lstrip('@'), max_len=100) if raw_user else ""
            if not target_user:
                self._send_json(400, {"error": "Missing or invalid 'user' parameter"})
                return
            pieruta_targets[target_user.lower()] = True
            self._send_json(200, {"success": True, "target": target_user, "message": f"Fart background queued for @{target_user}'s next message"})
            return

        # Kill Counter Update (requires counter token or auth)
        if path == "/api/counter":
            if not counter_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            req_token = self._get_request_auth_token()
            if config.kill_counter_api_token:
                if req_token != config.kill_counter_api_token and not dashboard_auth_manager.verify_session(req_token):
                    self._send_json(401, {"error": "Unauthorized: Invalid counter API token", "auth_required": True})
                    return
            elif dashboard_auth_manager.is_auth_required():
                if not self._check_auth():
                    return
            channel = sanitize_identifier(body.get("channel", ""), max_len=100) if body.get("channel") else ""
            if "increment" in body or "delta" in body:
                amt = sanitize_int(body.get("increment", body.get("delta", 1)), default=1, min_val=-1000, max_val=1000)
                res = kill_counter_monitor.increment(amt, channel=channel)
                self._send_json(200, res)
                return
            if "count" in body or "set" in body:
                cnt = sanitize_int(body.get("count", body.get("set", 0)), default=0, min_val=0, max_val=1000000)
                trigger = sanitize_bool(body.get("trigger_tts", False), default=False)
                res = kill_counter_monitor.set_count(cnt, trigger_tts=trigger, channel=channel)
                self._send_json(200, res)
                return
            verse = kill_counter_monitor.trigger_bible_tts(channel=channel)
            self._send_json(200, {"success": True, "count": kill_counter_monitor.current_count, "verse": verse})
            return

        # Kill Counter Test
        if path == "/api/counter/test":
            if not counter_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            req_token = self._get_request_auth_token()
            if config.kill_counter_api_token:
                if req_token != config.kill_counter_api_token and not dashboard_auth_manager.verify_session(req_token):
                    self._send_json(401, {"error": "Unauthorized: Invalid counter API token", "auth_required": True})
                    return
            elif dashboard_auth_manager.is_auth_required():
                if not self._check_auth():
                    return
            channel = sanitize_identifier(body.get("channel", ""), max_len=100) if body.get("channel") else ""
            verse = kill_counter_monitor.trigger_bible_tts(channel=channel)
            self._send_json(200, {"success": True, "count": kill_counter_monitor.current_count, "verse": verse})
            return

        # Proxy POST /api/tts (rate-limited, public)
        if path == "/api/tts":
            if not tts_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            text = sanitize_string(body.get("text"), max_len=2000)
            voice = sanitize_identifier(body.get("voice"), max_len=100) if body.get("voice") is not None else None
            model = sanitize_identifier(body.get("model"), max_len=100) if body.get("model") is not None else None
            fmt = sanitize_audio_format(body.get("format")) if body.get("format") is not None else None

            has_8d_api = False
            if text and re.search(r'\{\s*8d\s*\}', text, re.IGNORECASE):
                has_8d_api = True
                text = re.sub(r'\{\s*8d\s*\}', '', text, flags=re.IGNORECASE).strip()

            if not text:
                self._send_json(400, {"error": "Missing required field 'text'"})
                return
            try:
                audio_bytes, mime_type = tts_client.synthesize(
                    text=text, voice=voice, model=model, audio_format=fmt, method="POST"
                )
                if has_8d_api and getattr(config, "enable_8d_audio", True):
                    audio_bytes, mime_type = apply_8d_audio_effect(audio_bytes, audio_format=fmt or config.tts_format)
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
                logger.error(f"POST /api/tts error on public server: {e}")
                self._send_json(500, {"error": "TTS synthesis failed"})
            return

        # Upload New Soundboard Effect (Strict sanitization + Streamer name password check)
        if path == "/api/soundboard/upload":
            if not soundboard_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Upload rate limit exceeded. Please wait a minute before uploading another sound."})
                return
            if not config.enable_soundboard:
                self._send_json(400, {"error": "Soundboard is currently disabled."})
                return

            file_bytes, filename, custom_sound_name, password = extract_upload_payload(self.headers, post_data, body)

            active_chans = list(twitch_bot.channels) if twitch_bot and twitch_bot.channels else ([config.twitch_channel] if config.twitch_channel else [])
            if not verify_streamer_password(password, active_chans):
                self._send_json(401, {
                    "error": "Unauthorized: Streamer Password must match an active connected Twitch channel name (e.g. shroud)."
                })
                return

            try:
                clean_sound_name, clean_filename = validate_and_sanitize_audio_upload(
                    file_bytes=file_bytes,
                    filename=filename,
                    custom_sound_name=custom_sound_name
                )
            except ValueError as ve:
                self._send_json(400, {"error": str(ve)})
                return

            saved_name, file_path = soundboard_manager.save_uploaded_sound(
                clean_sound_name=clean_sound_name,
                clean_filename=clean_filename,
                file_bytes=file_bytes
            )

            broadcast_event("soundboard_updated", {
                "action": "upload",
                "sound_name": saved_name,
                "sounds": list(soundboard_manager.get_available_sounds().keys())
            })

            self._send_json(200, {
                "success": True,
                "message": f"Soundboard effect '({saved_name})' uploaded successfully!",
                "sound_name": saved_name,
                "audio_url": f"/api/soundboard/{saved_name}"
            })
            return


        # ── Authenticated POST routes (user role required) ──
        if not self._check_auth(required_role="user"):
            return

        # Soundboard Trigger (user role required when auth enabled)
        if path in ("/api/soundboard/trigger", "/api/soundboard/play"):
            if not soundboard_limiter.check_and_record(self._get_client_ip()):
                self._send_json(429, {"error": "Rate limit exceeded. Try again later."})
                return
            if not config.enable_soundboard:
                self._send_json(400, {"error": "Soundboard is currently disabled"})
                return
            raw_sound = body.get("sound") or body.get("sound_name") or body.get("name") or ""
            clean_sound = sanitize_identifier(raw_sound, max_len=100)
            if not clean_sound:
                self._send_json(400, {"error": "Missing or invalid 'sound' parameter"})
                return
            sound_match = soundboard_manager.find_sound(clean_sound)
            if not sound_match:
                self._send_json(404, {"error": f"Soundboard effect '{clean_sound}' not found"})
                return
            matched_name, file_path = sound_match
            req_chan = sanitize_string(body.get("channel") or config.twitch_channel, max_len=100)
            user = sanitize_string(body.get("user", "Control Portal"), max_len=50, default="Control Portal")
            sb_chunk = {
                "id": f"sb_{int(time.time()*1000)}",
                "url": f"/api/soundboard/{matched_name}",
                "speaker": user,
                "text": f"({matched_name})",
                "voice": "Soundboard",
                "channel": req_chan,
                "timestamp": time.time(),
                "is_soundboard": True
            }
            broadcast_event("audio_chunk", sb_chunk)
            broadcast_event("soundboard_trigger", {
                "sound_name": matched_name,
                "file_path": f"/api/soundboard/{matched_name}",
                "user": user,
                "channel": req_chan,
                "timestamp": time.time()
            })
            self._send_json(200, {
                "success": True,
                "sound_name": matched_name,
                "audio_url": f"/api/soundboard/{matched_name}",
                "channel": req_chan
            })
            return


        # Soundboard Toggle (authenticated)
        if path == "/api/soundboard/toggle":
            if "enabled" in body:
                config.enable_soundboard = sanitize_bool(body["enabled"], default=config.enable_soundboard)
            else:
                config.enable_soundboard = not config.enable_soundboard
            config.save()
            broadcast_event("status", self._get_public_status_dict())
            self._send_json(200, {"success": True, "enabled": config.enable_soundboard})
            return

        # Save user/control settings
        if path == "/api/control/settings":
            target_chan = sanitize_string(body.get("channel") or body.get("twitch_channel") or "", max_len=100)
            settings_to_update = {}
            if "enable_8d_audio" in body:
                settings_to_update["enable_8d_audio"] = sanitize_bool(body["enable_8d_audio"], default=config.enable_8d_audio)
            if "effect_8d_speed" in body:
                settings_to_update["effect_8d_speed"] = sanitize_float(body["effect_8d_speed"], default=config.effect_8d_speed, min_val=0.01, max_val=5.0)
            if "same_user_timeout" in body:
                settings_to_update["same_user_timeout"] = sanitize_float(body["same_user_timeout"], default=config.same_user_timeout, min_val=0.0, max_val=300.0)
            if "enable_chat_responses" in body:
                settings_to_update["enable_chat_responses"] = sanitize_bool(body["enable_chat_responses"], default=config.enable_chat_responses)
            if "enable_kill_counter" in body:
                settings_to_update["enable_kill_counter"] = sanitize_bool(body["enable_kill_counter"], default=config.enable_kill_counter)
            if "enable_chaos_mode" in body or "chaos_mode" in body:
                raw_chaos = body.get("enable_chaos_mode", body.get("chaos_mode"))
                settings_to_update["enable_chaos_mode"] = sanitize_bool(raw_chaos, default=config.enable_chaos_mode)

            config.set_channel_settings(target_chan, settings_to_update)
            config.save()
            broadcast_event("status", self._get_public_status_dict())
            eff_cfg = config.get_channel_settings(target_chan)
            broadcast_event("chaos_mode_update", {"chaos_mode": eff_cfg.get("enable_chaos_mode"), "channel": target_chan})
            self._send_json(200, {"success": True, "channel": target_chan, "config": eff_cfg})
            return

        # Toggle Chaos Mode directly
        if path in ("/api/chaos", "/api/chaos/toggle"):
            target_chan = sanitize_string(body.get("channel") or "", max_len=100)
            chan_cfg = config.get_channel_settings(target_chan)
            curr_chaos = chan_cfg.get("enable_chaos_mode", config.enable_chaos_mode)
            if "enabled" in body:
                new_chaos = sanitize_bool(body["enabled"], default=curr_chaos)
            elif "enable_chaos_mode" in body:
                new_chaos = sanitize_bool(body["enable_chaos_mode"], default=curr_chaos)
            else:
                new_chaos = not curr_chaos
            config.set_channel_settings(target_chan, {"enable_chaos_mode": new_chaos})
            config.save()
            broadcast_event("status", self._get_public_status_dict())
            broadcast_event("chaos_mode_update", {"chaos_mode": new_chaos, "channel": target_chan})
            self._send_json(200, {"success": True, "channel": target_chan, "chaos_mode": new_chaos})
            return

        # Connect Twitch Channel
        if path == "/api/connect":
            raw_chan = body.get("channel")
            sanitized = sanitize_channels_list(raw_chan)
            if not sanitized:
                self._send_json(400, {"error": "Valid Twitch channel name(s) required (up to 2 alphanumeric/underscore channels)"})
                return
            config.twitch_channel = sanitized
            config.save()
            if twitch_bot:
                twitch_bot.set_channel(sanitized)
            broadcast_event("status", self._get_public_status_dict())
            self._send_json(200, {"success": True, "channel": config.twitch_channel, "channels": config.channels})
            return

        # Skip Audio
        if path in ("/api/queue/skip", "/api/skip"):
            user = sanitize_string(body.get("user", "Dashboard"), max_len=50, default="Dashboard")
            broadcast_event("skip_audio", {"user": user, "channel": config.twitch_channel, "timestamp": time.time()})
            skip_msg = f"⏭️ Audio skipped by {user}."
            broadcast_event("chat_message", {"user": "System", "message": skip_msg, "channel": config.twitch_channel, "timestamp": time.time()})
            self._send_json(200, {"success": True, "message": "Audio skip triggered."})
            return

        # Clear Audio Queue
        if path == "/api/queue/clear":
            audio_queue.clear()
            broadcast_event("clear_audio", {"user": "Dashboard", "timestamp": time.time()})
            self._send_json(200, {"success": True, "message": "Audio queue cleared."})
            return

        # Test TTS
        if path == "/api/tts/test":
            text = sanitize_string(body.get("text"), max_len=2000)
            voice = sanitize_identifier(body.get("voice"), max_len=100) if body.get("voice") is not None else None
            model = sanitize_identifier(body.get("model"), max_len=100) if body.get("model") is not None else None
            user = sanitize_string(body.get("user", "TestUser"), max_len=50, default="TestUser")
            req_chan = sanitize_string(body.get("channel"), max_len=100) if body.get("channel") else ""
            if not text:
                self._send_json(400, {"error": "Text is required"})
                return
            threading.Thread(
                target=process_incoming_text,
                kwargs={"user": user, "raw_text": text, "override_voice": voice, "override_model": model, "channel": req_chan},
                daemon=True
            ).start()
            self._send_json(200, {"success": True, "message": "Test TTS job queued.", "channel": req_chan})
            return


        # User Voices Management
        if path == "/api/user_voices/set":
            username = sanitize_username(body.get("user"))
            voice = sanitize_identifier(body.get("voice"), max_len=100)
            locked = bool(body.get("locked", False))
            if not username or not voice:
                self._send_json(400, {"error": "Both valid 'user' and 'voice' parameters are required"})
                return
            saved = user_voice_manager.set_voice(username, voice, locked=locked, force=True)
            broadcast_event("status", self._get_public_status_dict())
            self._send_json(200, {"success": True, "user": username, "voice": saved, "user_voices": user_voice_manager.get_all()})
            return

        if path == "/api/user_voices/delete":
            username = sanitize_username(body.get("user"))
            if not username:
                self._send_json(400, {"error": "Valid parameter 'user' is required"})
                return
            user_voice_manager.clear_user(username)
            broadcast_event("status", self._get_public_status_dict())
            self._send_json(200, {"success": True, "user_voices": user_voice_manager.get_all()})
            return

        if path == "/api/user_voices/clear":
            user_voice_manager.clear_all()
            broadcast_event("status", self._get_public_status_dict())
            self._send_json(200, {"success": True, "user_voices": {}})
            return

        self.send_error(404, "Not Found")

    def _get_public_status_dict(self) -> dict:
        """Return sanitized status dict safe for internet exposure (no admin creds, no infrastructure, no TTS API URL)."""
        return get_public_status_dict()

    def _send_json(self, code: int, data: dict, cookies: list = None):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookies:
            for c in cookies:
                self.send_header("Set-Cookie", c)
        self._send_cors_headers()
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_static_file(self, filepath: str, mime_type: str, allow_framing: bool = False):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self._send_cors_headers()
            self._send_security_headers(allow_framing=allow_framing)
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error reading static file {filepath} on public server: {e}")
            self.send_error(500, "Internal server error")


class OBSRequestHandler(BaseHTTPRequestHandler):
    """Dedicated read-only handler for OBS Overlay Browser Source."""

    def log_message(self, format, *args):
        pass

    def version_string(self):
        """Override to suppress server version fingerprinting (OWASP A05:2021)."""
        return "TwitchTTS"

    def _get_client_ip(self) -> str:
        return self.client_address[0] if self.client_address else "unknown"

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; media-src 'self' blob: data:; connect-src 'self' ws: wss:; img-src 'self' data: blob:; object-src 'none'; frame-ancestors *;")

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_error(405, "Method Not Allowed")

    def do_PUT(self):
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        self.send_error(405, "Method Not Allowed")

    def do_PATCH(self):
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):
        self.send_error(405, "Method Not Allowed")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/obs", "/obs.html"):
            safe_path = os.path.join(STATIC_DIR, "obs.html")
            self._serve_file(safe_path, "text/html; charset=utf-8")
            return
        if path == "/obs.css":
            safe_path = os.path.join(STATIC_DIR, "obs.css")
            self._serve_file(safe_path, "text/css")
            return
        if path == "/obs.js":
            safe_path = os.path.join(STATIC_DIR, "obs.js")
            self._serve_file(safe_path, "application/javascript")
            return
        if path == "/darkcounter_obs.lua":
            parsed_obs = urllib.parse.urlparse(self.path)
            query_obs = urllib.parse.parse_qs(parsed_obs.query)
            serve_darkcounter_lua(self, query_obs)
            return

        if path.startswith("/api/audio/"):
            chunk_id = path[len("/api/audio/"):]
            if chunk_id in audio_store:
                audio_bytes, mime_type, _ = audio_store[chunk_id]
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(audio_bytes)))
                self._send_security_headers()
                self.end_headers()
                self.wfile.write(audio_bytes)
                return
            else:
                self.send_error(404, "Audio chunk not found")
                return

        if path == "/api/events":
            handle_sse_stream(self, is_admin=False)
            return

        self.send_error(404, "Not Found")

    def _serve_file(self, filepath: str, mime_type: str):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, "Internal server error")


def run_server(host: str = "0.0.0.0", port: int = 5000, public_host: str = "0.0.0.0", public_port: int = 5001):
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

    # Start Kill Counter Monitor background thread
    kill_counter_monitor.process_text_func = process_incoming_text
    kill_counter_monitor.broadcast_func = broadcast_event
    kill_counter_monitor.start()

    # Start unified Public Web Server (control portal, player, OBS overlay)
    public_httpd = None
    if public_port != port:
        public_address = (public_host, public_port)
        public_httpd = ThreadingHTTPServer(public_address, PublicRequestHandler)
        public_thread = threading.Thread(target=public_httpd.serve_forever, daemon=True)
        public_thread.start()
        logger.info(f"Public Web Server running on http://{public_host}:{public_port}/ (Control Portal, Player, OBS Overlay)")

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TTSRequestHandler)
    logger.info(f"Admin Dashboard Server running on http://{host}:{port} (Private)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping servers...")
    finally:
        kill_counter_monitor.stop()
        if twitch_bot:
            twitch_bot.stop()
        if public_httpd:
            public_httpd.server_close()
        httpd.server_close()
