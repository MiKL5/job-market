import re
import unicodedata

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

_TOPIC    = re.compile(r"(?<![a-z0-9])(data|ia|ai|intelligence artificielle)(?![a-z0-9])")
_CONTRACT = re.compile(r"(?<![a-z0-9])(alternan\w*|alternance|stage\w*|stagiaire)(?![a-z0-9])")

def title_matches(title) -> bool:
    """Intitule contenant (data | IA | intelligence artificielle) ET (alternant/alternance | stage)."""
    t = strip_accents((title or "").lower())
    return bool(_TOPIC.search(t)) and bool(_CONTRACT.search(t))