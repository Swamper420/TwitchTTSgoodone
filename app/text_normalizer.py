import re

COMMON_EMOTES = {
    "kappa", "pogchamp", "lul", "monkas", "pepehands", "biblethump",
    "kreygasm", "ResidentSleeper", "4head", "pog", "pepega", "omgscoots"
}

ABBREVIATIONS = {
    r'\bbrb\b': 'be right back',
    r'\bbtw\b': 'by the way',
    r'\bgg\b': 'good game',
    r'\blol\b': 'laugh out loud',
    r'\brofl\b': 'rolling on the floor laughing',
    r'\bomg\b': 'oh my god',
    r'\bimo\b': 'in my opinion',
    r'\bafk\b': 'away from keyboard',
    r'\bw/\b': 'with',
    r'\bw/o\b': 'without',
    r'\btbh\b': 'to be honest',
    r'\bnp\b': 'no problem',
    r'\bty\b': 'thank you',
    r'\bpls\b': 'please',
    r'\bplz\b': 'please',
}

def normalize_text(text: str) -> str:
    """
    Advanced text normalizer:
    1. Expands Twitch abbreviations (brb -> be right back)
    2. Expands currencies ($50 -> 50 dollars, €20 -> 20 euros, £10 -> 10 pounds)
    3. Expands numeric abbreviations (100k -> 100 thousand)
    4. Strips Twitch emotes
    """
    if not text:
        return ""
    
    # 1. Expand Currencies
    text = re.sub(r'\$(\d+(?:\.\d+)?)', r'\1 dollars', text)
    text = re.sub(r'€(\d+(?:\.\d+)?)', r'\1 euros', text)
    text = re.sub(r'£(\d+(?:\.\d+)?)', r'\1 pounds', text)
    
    # 2. Expand Numeric shorthand (e.g. 50k -> 50 thousand)
    text = re.sub(r'\b(\d+)k\b', r'\1 thousand', text, flags=re.IGNORECASE)
    text = re.sub(r'\b#(\d+)\b', r'number \1', text)
    
    # 3. Expand Abbreviations
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
    # 4. Strip common Twitch emotes
    words = text.split()
    cleaned_words = [w for w in words if w.lower() not in COMMON_EMOTES]
    text = " ".join(cleaned_words)
    
    return text
