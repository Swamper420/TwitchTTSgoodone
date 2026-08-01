import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class TTSChunk:
    text: str
    voice: Optional[str] = None
    chunk_index: int = 0
    total_chunks: int = 1


from app.config import config
from app.text_normalizer import normalize_text

def sanitize_text(text: str) -> str:
    """Sanitize message text by normalizing abbreviations/currencies, stripping URLs, control chars, and excessive repeating characters."""
    if not text:
        return ""
    
    # Strip null bytes, control characters, and non-printable unicode ranges that trigger special token errors
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffe\uffff]', '', text)
    
    # Advanced text normalization (currencies, numbers, abbreviations, emotes)
    text = normalize_text(text)
    
    # Strip URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    
    # Reduce character repetition (e.g., "looooool" -> "loool")
    text = re.sub(r'(.)\1{3,}', r'\1\1\1', text)
    
    # Reduce excessive punctuation (e.g. "!!!" -> "!")
    text = re.sub(r'([!?.])\1+', r'\1', text)
    
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
    # Match pattern like [voice_name]
    pattern = r'\[([a-zA-Z0-9_\-]+)\]'
    tokens = re.split(pattern, text)
    
    # re.split with 1 group returns: [text_before, group_1, text_after, group_2, text_after...]
    segments: List[Tuple[Optional[str], str]] = []
    
    current_voice: Optional[str] = None
    first_part = tokens[0].strip() if tokens else ""
    if first_part:
        segments.append((None, first_part))
        
    i = 1
    while i < len(tokens):
        voice_name = tokens[i].strip()
        segment_text = tokens[i + 1].strip() if (i + 1) < len(tokens) else ""
        if segment_text:
            segments.append((voice_name, segment_text))
        current_voice = voice_name
        i += 2
        
    return segments


def split_text_into_chunks(text: str, max_chars: Optional[int] = None) -> List[str]:
    """Split text into chunks by sentence boundaries, clauses, and word boundaries."""
    if max_chars is None:
        max_chars = config.max_chunk_chars
    sanitized = sanitize_text(text)
    if not sanitized:
        return []
    
    if len(sanitized) <= max_chars:
        return [sanitized]
    
    # Step 1: Split into sentences (. ! ? \n)
    sentence_pattern = r'(?<=[.!?\n])\s+'
    raw_sentences = [s.strip() for s in re.split(sentence_pattern, sanitized) if s.strip()]
    
    chunks: List[str] = []
    
    for sentence in raw_sentences:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
            
        # Step 2: Split long sentence by clauses (, ; : -)
        clause_pattern = r'(?<=[,;:-])\s+'
        raw_clauses = [c.strip() for c in re.split(clause_pattern, sentence) if c.strip()]
        
        current_chunk = ""
        for clause in raw_clauses:
            if len(clause) > max_chars:
                # Flush existing chunk
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                # Step 3: Hard split at word boundaries
                words = clause.split()
                sub_chunk = ""
                for word in words:
                    if len(sub_chunk) + len(word) + 1 <= max_chars:
                        sub_chunk = f"{sub_chunk} {word}".strip()
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk)
                        sub_chunk = word
                if sub_chunk:
                    chunks.append(sub_chunk)
            else:
                if len(current_chunk) + len(clause) + 1 <= max_chars:
                    current_chunk = f"{current_chunk} {clause}".strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = clause
        if current_chunk:
            chunks.append(current_chunk)
            
    return chunks


def ensure_min_length(text: str, min_length: Optional[int] = None) -> str:
    """Ensure text is at least min_length characters long by padding with trailing dots."""
    if min_length is None:
        min_length = config.min_chunk_chars
    if not text:
        return "." * min_length
    if len(text) < min_length:
        needed = min_length - len(text)
        return text + "." * needed
    return text


def process_message_to_chunks(text: str, max_chars: Optional[int] = None, min_chars: Optional[int] = None) -> List[TTSChunk]:
    """
    Full message processing pipeline:
    1. Parse [voice] tags
    2. Sanitize and chunk each voice segment
    3. Ensure minimum characters per chunk
    4. Return TTSChunk objects with index tracking
    """
    if max_chars is None:
        max_chars = config.max_chunk_chars
    if min_chars is None:
        min_chars = config.min_chunk_chars

    voice_segments = parse_voice_tags(text)
    all_chunks: List[TTSChunk] = []
    
    temp_chunks: List[Tuple[Optional[str], str]] = []
    for voice, seg_text in voice_segments:
        sub_chunks = split_text_into_chunks(seg_text, max_chars=max_chars)
        for sub in sub_chunks:
            padded_sub = ensure_min_length(sub, min_length=min_chars)
            temp_chunks.append((voice, padded_sub))
            
    total = len(temp_chunks)
    for idx, (voice, chunk_text_val) in enumerate(temp_chunks):
        all_chunks.append(
            TTSChunk(
                text=chunk_text_val,
                voice=voice,
                chunk_index=idx,
                total_chunks=total
            )
        )
        
    return all_chunks

