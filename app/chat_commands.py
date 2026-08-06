import logging
from typing import Dict, List, Optional, Tuple, Any

try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

logger = logging.getLogger("ChatCommands")

# Registry of canonical command names -> list of supported aliases/triggers
COMMAND_ALIASES: Dict[str, List[str]] = {
    "help": ["!help", "!tts", "!botinfo", "!info", "!about", "!ohje", "!komennot", "!commands"],
    "voices": ["!voices", "!preset", "!presets", "!äänikö", "!äänet"],
    "sounds": ["!soundboard", "!sounds", "!sound", "!sfx", "!effects", "!soundslist", "!audioeffects", "!efektit"],
    "skip": ["!skip", "!next", "!ohita", "!skippa", "!skippaa", "!seuraava"],
    "clear": ["!clear", "!clearqueue", "!stop", "!tyhjennä"],
    "pieruta": ["!pieruta", "!fart", "!pieru"],
    "myvoice": ["!myvoice", "!voice", "!omaääni"],
}

# Reverse lookup: alias -> canonical command name
ALIAS_TO_COMMAND: Dict[str, str] = {}
ALL_COMMAND_ALIASES: List[str] = []
for canonical, aliases in COMMAND_ALIASES.items():
    for alias in aliases:
        lower_alias = alias.lower()
        ALIAS_TO_COMMAND[lower_alias] = canonical
        if lower_alias not in ALL_COMMAND_ALIASES:
            ALL_COMMAND_ALIASES.append(lower_alias)

# Natural language sound queries
SOUND_QUERY_PHRASES = (
    "what sound effects", "which sound effects", "list sound effects",
    "available sound effects", "show sound effects", "what sounds",
    "mitä soundeja", "mitä ääniefektejä", "mitä efektejä"
)

# Keyword aliases for myvoice actions
RANDOM_VOICE_ALIASES = ["random", "rand", "rng", "satunnainen", "?"]
RESET_VOICE_ALIASES = ["reset", "clear", "default", "none", "nollaa", "poista"]


def parse_chat_command(raw_text: str, score_cutoff: float = 78.0) -> Optional[Tuple[str, str, float]]:
    """
    Parses a raw chat message into a canonical command name, argument string, and confidence score.
    Returns (canonical_command, args_str, score) if recognized, or None if not a command.

    Example:
    '!helpp' -> ('help', '', 90.9)
    '!myvois mieto' -> ('myvoice', 'mieto', 80.0)
    '!skp' -> ('skip', '', 88.9)
    '!pierut @user' -> ('pieruta', '@user', 93.3)
    """
    if not raw_text:
        return None

    cleaned_text = raw_text.strip()
    if not cleaned_text:
        return None

    raw_lower = cleaned_text.lower()

    # Special handling: natural language sound queries without ! prefix
    if any(phrase in raw_lower for phrase in SOUND_QUERY_PHRASES):
        return ("sounds", "", 100.0)

    # Must start with '!' to be considered a command candidate
    if not cleaned_text.startswith("!"):
        return None

    # Separate command token from arguments
    parts = cleaned_text.split(maxsplit=1)
    cmd_token = parts[0].strip().lower()
    args_str = parts[1].strip() if len(parts) > 1 else ""

    # 1. Exact match against known aliases
    if cmd_token in ALIAS_TO_COMMAND:
        return (ALIAS_TO_COMMAND[cmd_token], args_str, 100.0)

    # Special prefix rules for sounds (e.g. !soundeffect or !sfxlist)
    if any(k in cmd_token for k in ("sound", "sfx", "effect")):
        return ("sounds", args_str, 100.0)

    # 2. Fuzzy match via RapidFuzz
    if HAS_RAPIDFUZZ and len(cmd_token) >= 2:
        match = process.extractOne(
            cmd_token,
            ALL_COMMAND_ALIASES,
            scorer=fuzz.WRatio,
            score_cutoff=score_cutoff
        )
        if match:
            best_alias, score, _ = match
            canonical = ALIAS_TO_COMMAND[best_alias]
            logger.info(f"Fuzzy matched chat command '{cmd_token}' -> '{best_alias}' ({canonical}) [score: {score:.1f}]")
            return (canonical, args_str, float(score))

    return None


def match_voice_preset(requested_voice: str, available_presets: List[str], score_cutoff: float = 75.0) -> Optional[Tuple[str, float]]:
    """
    Fuzzy matches requested_voice string against available preset voices list.
    Returns (matched_preset_name, score) or None.
    """
    cleaned = requested_voice.strip()
    if not cleaned or not available_presets:
        return None

    # Exact match (case-insensitive)
    cleaned_lower = cleaned.lower()
    for preset in available_presets:
        if preset.lower() == cleaned_lower:
            return (preset, 100.0)

    # RapidFuzz match
    if HAS_RAPIDFUZZ:
        match = process.extractOne(
            cleaned_lower,
            [p.lower() for p in available_presets],
            scorer=fuzz.WRatio,
            score_cutoff=score_cutoff
        )
        if match:
            matched_lower, score, index = match
            best_preset = available_presets[index]
            logger.info(f"Fuzzy matched voice preset '{requested_voice}' -> '{best_preset}' [score: {score:.1f}]")
            return (best_preset, float(score))

    return None


def match_voice_action(raw_arg: str, score_cutoff: float = 75.0) -> Optional[Tuple[str, float]]:
    """
    Matches voice command argument (e.g., 'random', 'reset') with exact/fuzzy logic.
    Returns ('random', score) or ('reset', score) or None.
    """
    cleaned = raw_arg.strip().lower()
    if not cleaned:
        return None

    if cleaned in RANDOM_VOICE_ALIASES:
        return ("random", 100.0)
    if cleaned in RESET_VOICE_ALIASES:
        return ("reset", 100.0)

    if HAS_RAPIDFUZZ:
        m_random = process.extractOne(cleaned, RANDOM_VOICE_ALIASES, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
        m_reset = process.extractOne(cleaned, RESET_VOICE_ALIASES, scorer=fuzz.WRatio, score_cutoff=score_cutoff)

        score_rand = m_random[1] if m_random else 0.0
        score_reset = m_reset[1] if m_reset else 0.0

        if score_rand >= score_cutoff and score_rand >= score_reset:
            logger.info(f"Fuzzy matched voice action '{raw_arg}' -> 'random' [score: {score_rand:.1f}]")
            return ("random", float(score_rand))
        elif score_reset >= score_cutoff:
            logger.info(f"Fuzzy matched voice action '{raw_arg}' -> 'reset' [score: {score_reset:.1f}]")
            return ("reset", float(score_reset))

    return None


def get_commands_catalog() -> List[Dict[str, Any]]:
    """Return catalog of available chat commands with category, syntax, aliases, description, and examples."""
    return [
        {
            "name": "help",
            "category": "General",
            "syntax": "!help",
            "aliases": COMMAND_ALIASES.get("help", []),
            "description": "Displays information about available TTS commands and usage guidelines in chat.",
            "example": "!help",
        },
        {
            "name": "myvoice",
            "category": "Voice Controls",
            "syntax": "!myvoice <voice_name | random | reset>",
            "aliases": COMMAND_ALIASES.get("myvoice", []),
            "description": "Sets or clears your custom TTS voice preset. Use 'random' for a random voice or 'reset' to revert to default.",
            "example": "!myvoice mieto",
        },
        {
            "name": "voices",
            "category": "Voice Controls",
            "syntax": "!voices",
            "aliases": COMMAND_ALIASES.get("voices", []),
            "description": "Lists all available voice presets in Twitch chat.",
            "example": "!voices",
        },
        {
            "name": "sounds",
            "category": "Soundboard",
            "syntax": "!sounds",
            "aliases": COMMAND_ALIASES.get("sounds", []),
            "description": "Lists all available soundboard sound effects in chat.",
            "example": "!sounds",
        },
        {
            "name": "sound_trigger",
            "category": "Soundboard",
            "syntax": "(soundname)",
            "aliases": ["(boom)", "(bruh)", "(fart)", "..."],
            "description": "Play a soundboard effect inline inside any message by placing the sound name in parentheses.",
            "example": "Hello world (boom) cheers! (bruh)",
        },
        {
            "name": "skip",
            "category": "Playback Controls",
            "syntax": "!skip",
            "aliases": COMMAND_ALIASES.get("skip", []),
            "description": "Skips the currently playing TTS audio message.",
            "example": "!skip",
        },
        {
            "name": "clear",
            "category": "Playback Controls",
            "syntax": "!clear",
            "aliases": COMMAND_ALIASES.get("clear", []),
            "description": "Clears all pending TTS audio messages from the queue.",
            "example": "!clear",
        },
        {
            "name": "pieruta",
            "category": "Fun / Effects",
            "syntax": "!pieruta [@target]",
            "aliases": COMMAND_ALIASES.get("pieruta", []),
            "description": "Fart effect command targeting yourself or another chat member.",
            "example": "!pieruta @user",
        },
    ]

