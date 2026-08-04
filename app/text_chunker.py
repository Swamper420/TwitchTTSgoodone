import re
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class TTSChunk:
    text: str
    voice: Optional[str] = None
    chunk_index: int = 0
    total_chunks: int = 1
    is_soundboard: bool = False
    sound_file: Optional[str] = None
    sound_name: Optional[str] = None


from app.config import config
from app.text_normalizer import normalize_text

def sanitize_text(text: str) -> str:
    """Sanitize message text by normalizing abbreviations/currencies, stripping URLs, control chars, and excessive whitespace."""
    if not text:
        return ""

    # Strip null bytes, control characters, and non-printable unicode ranges that trigger special token errors
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffe\uffff]', '', text)

    # Strip {8D} tags
    text = re.sub(r'\{\s*8d\s*\}', '', text, flags=re.IGNORECASE)

    # Advanced text normalization (currencies, numbers, abbreviations, emotes)
    text = normalize_text(text)

    # Strip URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)

    # Reduce character repetition (e.g., "looooool" -> "loool")
    text = re.sub(r'(.)\1{3,}', r'\1\1\1', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_voice_tags(text: str) -> List[Tuple[Optional[str], str]]:
    """
    Parse [voicename] tags from text and return a list of (voice_name, segment_text) tuples.
    Example:
    "Hello world [alice] this is Alice speaking [bob] and this is Bob!"
    -> [(None, "Hello world"), ("alice", "this is Alice speaking"), ("bob", "and this is Bob!")]
    """
    pattern = r'\[([a-zA-Z0-9_\-]+)\]'
    tokens = re.split(pattern, text)

    segments: List[Tuple[Optional[str], str]] = []

    first_part = tokens[0].strip() if tokens else ""
    if first_part:
        segments.append((None, first_part))

    i = 1
    while i < len(tokens):
        voice_name = tokens[i].strip()
        segment_text = tokens[i + 1].strip() if (i + 1) < len(tokens) else ""
        if segment_text:
            segments.append((voice_name, segment_text))
        i += 2

    return segments


def split_text_into_chunks(text: str, max_chars: Optional[int] = None) -> List[str]:
    """Deprecated chunking helper - returns sanitized text in a single item without splitting."""
    sanitized = sanitize_text(text)
    return [sanitized] if sanitized else []


def ensure_min_length(text: str, min_length: Optional[int] = None) -> str:
    """Deprecated length helper - returns text unmodified without dot padding."""
    return text or ""


def parse_shouting_segments(text: str) -> List[Tuple[bool, str]]:
    """
    Parse text into segments of (is_shouting, segment_text).
    Identifies contiguous ALLCAPS words and assigns True to is_shouting.
    """
    if not text:
        return []

    tokens = [t for t in re.split(r'(\s+|[^\w\s]+)', text) if t]
    if not tokens:
        return []

    token_types = []
    has_normal_words = False

    for t in tokens:
        if any(c.isalpha() for c in t):
            if t.isupper():
                n_alpha = sum(1 for c in t if c.isalpha())
                if n_alpha >= 2:
                    token_types.append("ALLCAPS")
                else:
                    token_types.append("SINGLE_UPPER")
            else:
                token_types.append("NORMAL")
                has_normal_words = True
        else:
            token_types.append("DELIMITER")

    has_allcaps = "ALLCAPS" in token_types

    is_shouting_word = []
    for idx, ttype in enumerate(token_types):
        if ttype == "ALLCAPS":
            is_shouting_word.append(True)
        elif ttype == "NORMAL":
            is_shouting_word.append(False)
        elif ttype == "SINGLE_UPPER":
            if not has_normal_words or has_allcaps:
                is_shouting_word.append(True)
            else:
                is_shouting_word.append(False)
        else:
            is_shouting_word.append(None)

    if not any(sw is True for sw in is_shouting_word):
        return [(False, text)]

    final_shouting = [False] * len(tokens)
    for idx, ttype in enumerate(token_types):
        if is_shouting_word[idx] is True:
            final_shouting[idx] = True
        elif is_shouting_word[idx] is False:
            final_shouting[idx] = False

    for idx, ttype in enumerate(token_types):
        if ttype == "DELIMITER":
            left_shouting = False
            for l in range(idx - 1, -1, -1):
                if token_types[l] != "DELIMITER":
                    left_shouting = final_shouting[l]
                    break
            right_shouting = False
            for r in range(idx + 1, len(tokens)):
                if token_types[r] != "DELIMITER":
                    right_shouting = final_shouting[r]
                    break

            if left_shouting and right_shouting:
                final_shouting[idx] = True
            elif left_shouting and not right_shouting:
                if re.search(r'[^\s]', tokens[idx]):
                    final_shouting[idx] = True
                else:
                    final_shouting[idx] = False
            else:
                final_shouting[idx] = False

    segments: List[Tuple[bool, str]] = []
    curr_shouting = final_shouting[0]
    curr_text = []

    for idx, token in enumerate(tokens):
        sh = final_shouting[idx]
        if sh == curr_shouting:
            curr_text.append(token)
        else:
            seg_str = "".join(curr_text)
            if seg_str:
                segments.append((curr_shouting, seg_str))
            curr_shouting = sh
            curr_text = [token]

    if curr_text:
        seg_str = "".join(curr_text)
        if seg_str:
            segments.append((curr_shouting, seg_str))

    return segments


def process_message_to_chunks(text: str, **kwargs) -> List[TTSChunk]:
    """
    Full message processing pipeline without character chunking or dot padding:
    1. Parse [voice] tags
    2. Parse soundboard (soundname) triggers within each voice section
    3. Parse ALLCAPS shouting segments and assign randomly selected shouting voice
    4. Sanitize segment text (no splitting or padding)
    5. Return TTSChunk objects with index tracking
    """
    from app.soundboard import soundboard_manager

    voice_segments = parse_voice_tags(text)
    raw_chunks: List[dict] = []

    for voice, voice_text in voice_segments:
        sb_segments = soundboard_manager.parse_soundboard_text(voice_text)
        for sb_seg in sb_segments:
            if sb_seg["type"] == "soundboard":
                raw_chunks.append({
                    "is_soundboard": True,
                    "text": sb_seg["raw_trigger"],
                    "voice": voice,
                    "sound_file": sb_seg["file_path"],
                    "sound_name": sb_seg["sound_name"]
                })
            else:
                seg_text = sb_seg["content"]
                shout_segments = parse_shouting_segments(seg_text)
                for is_shout, shout_text in shout_segments:
                    shout_voices = config.shouting_voices_list
                    chunk_voice = random.choice(shout_voices) if is_shout and shout_voices else voice
                    sanitized_sub = sanitize_text(shout_text)
                    if sanitized_sub:
                        raw_chunks.append({
                            "is_soundboard": False,
                            "text": sanitized_sub,
                            "voice": chunk_voice,
                            "sound_file": None,
                            "sound_name": None
                        })

    total = len(raw_chunks)
    all_chunks: List[TTSChunk] = []

    for idx, item in enumerate(raw_chunks):
        all_chunks.append(
            TTSChunk(
                text=item["text"],
                voice=item["voice"],
                chunk_index=idx,
                total_chunks=total,
                is_soundboard=item["is_soundboard"],
                sound_file=item["sound_file"],
                sound_name=item["sound_name"]
            )
        )

    return all_chunks



