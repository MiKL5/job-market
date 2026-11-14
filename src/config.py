import os
from   pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)

def _float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)

CONTACT    = os.getenv("CONTACT_EMAIL", "contact@example.org")
USER_AGENT = f"ProjetETL-M1DataIA/1.0 (usage pedagogique; contact: {CONTACT})"
DELAY_S    = max(3.0, _float("REQUEST_DELAY_S", 4))          # plancher de 3 s pour le scraping
TIMEOUT_S  = 20

FT_BASE      = "https://candidat.francetravail.fr"
FT_MAX_PAGES = _int("FT_MAX_PAGES", 10)
FT_SAVE_HTML = os.getenv("FT_SAVE_HTML", "1") == "1"
# Pages de resultats "metier + ville" (statiques, indexees) ; codes releves sur le site : s28=Informatique et telecoms,
# m18=Data analyst, m15=Data scientist, v10=Lille.
FT_LISTING_URLS = [u.strip() for u in os.getenv("FT_LISTING_URLS", ",".join([
    f"{FT_BASE}/offres/emploi/data-analyst/lille/s28m18v10",
    f"{FT_BASE}/offres/emploi/data-scientist/lille/s28m15v10",
])).split(",") if u.strip()]

ADZUNA_ID        = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_KEY       = os.getenv("ADZUNA_APP_KEY", "")
ADZUNA_MAX_PAGES = _int("ADZUNA_MAX_PAGES", 3)
ADZUNA_DELAY_S   = _float("ADZUNA_DELAY_S", 1)
ADZUNA_WHERE     = [w.strip() for w in os.getenv("ADZUNA_WHERE", "Hauts-de-France").split(",") if w.strip()]

DB_BACKEND = os.getenv("DB_BACKEND", "postgres").lower()    # postgres (defaut, Docker) | sqlite en repli
_sp = Path(os.getenv("SQLITE_PATH", "data/jobmarket.db"))
SQLITE_PATH = _sp if _sp.is_absolute() else ROOT / _sp
PG = {
    "user": os.getenv("POSTGRES_USER", ""), "password": os.getenv("POSTGRES_PASSWORD", ""),
    "dbname": os.getenv("POSTGRES_DB", ""), "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

REGION             = "Hauts-de-France"
HDF_DEPARTEMENTS   = {"02": "Aisne", "59": "Nord", "60": "Oise", "62": "Pas-de-Calais", "80": "Somme"}
HDF_REGION_ALIASES = {"hauts de france", "nord pas de calais", "picardie"}
RAW_DIR            = ROOT / "data" / "raw"