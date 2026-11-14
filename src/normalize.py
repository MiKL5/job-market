import hashlib
import re
from   filters   import strip_accents
from   territory import DEPT_BY_NAME

_DEPT_PREFIX    = re.compile(r"^\s*(\d{2,3}|2[AB])\s*[-–/ ]\s*")
_POSTAL         = re.compile(r"\b(\d{5})\b")
_ARRONDISSEMENT = re.compile(r"\b(\d{1,2})(?:er|e|eme|ème)?\s*(?:arrondissement|arr\.?)\b", re.I)

def extract_hints(raw):
    """Retourne (code_postal, code_departement) trouves dans la localisation brute.
    Formes gerees : '59 - Lille', '59000 Lille', 'Lille, Nord' (nom de departement apres la virgule)."""
    if not raw:
        return None, None
    m = _POSTAL.search(raw)
    if m:
        return m.group(1), m.group(1)[:2]
    m = _DEPT_PREFIX.match(raw)
    if m:
        return None, m.group(1)
    for part in raw.split(",")[1:]:
        code = DEPT_BY_NAME.get(" ".join(strip_accents(part.lower()).replace("-", " ").split()))
        if code:
            return None, code
    return None, None

def clean_city_label(raw):
    """Libelle propre pour interroger l'API : 'Lille, Nord' -> 'Lille' ; '59 - Villeneuve-d'Ascq' -> 'Villeneuve-d'Ascq'."""
    if not raw:
        return None
    s = raw.split(",")[0]
    s = _POSTAL.sub(" ", s)
    s = _DEPT_PREFIX.sub("", s)
    s = _ARRONDISSEMENT.sub(" ", s)
    s = re.sub(r"\(.*?\)", " ", s)
    return " ".join(s.split()) or None

def normalize_city(raw):
    """'59 - Marquette-lez-Lille' -> 'marquette lez lille' ; 'St-Quentin (02)' -> 'saint quentin'."""
    if not raw:
        return None
    s = strip_accents(raw.split(",")[0].lower())
    s = _POSTAL.sub(" ", s)
    s = _DEPT_PREFIX.sub("", s)
    s = _ARRONDISSEMENT.sub(" ", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\bst\b", "saint", s)
    s = re.sub(r"\bste\b", "sainte", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s or None

def norm_text(raw):
    """Normalisation generique (casse, accents, ponctuation) pour comparer titres et entreprises."""
    if not raw:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(raw.lower())).strip()

def content_key(titre, entreprise, ville_norm):
    """Cle de dedoublonnage par contenu (inter-sources)."""
    key = "|".join([norm_text(titre), norm_text(entreprise), ville_norm or ""])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()
