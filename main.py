#!/usr/bin/env python3
"""
Twitch TTS Bot with Local TTS API Integration & Web Audio Player.
"""

import argparse
import logging
import sys

from app.config import config
from app.server import run_server

def main():
    parser = argparse.ArgumentParser(description="Twitch TTS Bot with Local TTS API")
    parser.add_argument("--channel", "-c", type=str, default=None, help="Twitch channel to join on startup")
    parser.add_argument("--port", "-p", type=int, default=None, help="Web server port")
    parser.add_argument("--tts-url", type=str, default=None, help="Local TTS API endpoint")
    parser.add_argument("--voice", type=str, default=None, help="Default voice override")
    parser.add_argument("--model", type=str, default=None, help="Default model override")
    parser.add_argument("--max-chunk", type=int, default=None, help="Max chunk size in characters")

    args = parser.parse_args()

    cli_updated = False
    if args.channel is not None:
        config.twitch_channel = args.channel
        cli_updated = True
    if args.port is not None:
        config.server_port = args.port
        cli_updated = True
    if args.tts_url is not None:
        config.tts_api_url = args.tts_url
        cli_updated = True
    if args.voice is not None:
        config.tts_voice = args.voice
        cli_updated = True
    if args.model is not None:
        config.tts_model = args.model
        cli_updated = True
    if args.max_chunk is not None:
        config.max_chunk_chars = args.max_chunk
        cli_updated = True

    if cli_updated:
        config.save()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    print("=" * 60)
    print(" 🎙️  TWITCH TTS BOT WITH LOCAL TTS API & WEB PLAYER")
    print("=" * 60)
    print(f" ► Web Interface:    http://localhost:{config.server_port}")
    print(f" ► Local TTS API:    {config.tts_api_url}")
    print(f" ► Twitch Channel:   #{config.twitch_channel if config.twitch_channel else '(None - enter in Web UI)'}")
    print(f" ► Max Chunk Chars:  {config.max_chunk_chars}")
    print("=" * 60)

    try:
        run_server(host=config.server_host, port=config.server_port)
    except KeyboardInterrupt:
        print("\nExiting Twitch TTS Bot. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
