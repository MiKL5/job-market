import hashlib
import logging
import re
from   datetime    import date, datetime, timedelta, timezone
from   bs4         import BeautifulSoup
from   config      import FT_BASE, FT_LISTING_URLS, FT_MAX_PAGES, FT_SAVE_HTML, RAW_DIR
from   polite_http import PoliteSession
from   robots      import Robots

log = logging.getLogger(__name__)
DETAIL_RE = re.compile(r"/offres/recherche/detail/([0-9A-Za-z]{5,10})")
LOC_RE    = re.compile(r"^(?:(?P<company>.+?)\s+-\s+)?(?P<dept>\d{2,3}|2[AB])\s+-\s+(?P<city>.+)$")
CONTRACTS = {"cdi", "cdd", "mis", "interim", "intérim", "profession libérale", "profession liberale",
             "franchise", "commercial", "contrat d'apprentissage", "contrat de professionnalisation",
             "saisonnier", "stage"}
NOISE    = {"(déjà vu)", "(deja vu)", "ajouter cette offre à ma sélection"}

def _clean(line):
    return re.sub(r"^[\s\-–—\u00a0]+|[\s\u00a0]+$", "", line or "")

def parse_published(text, today=None): # Format de date: 'Publié le 22/06/2024' -> date ; 'Publié il y a 22 jours' -> date ; 'aujourd'hui'/'hier' ; 'plus de 30 jours' -> None (inconnue).
    today = today or date.today()
    t = (text or "").lower()
    if "plus de" in t:
        return None
    if "aujourd" in t:
        return today
    if "hier" in t:
        return today - timedelta(days=1)
    m = re.search(r"il y a (\d+)\s*(jour|semaine|mois)", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return today - timedelta(days=n * {"jour": 1, "semaine": 7, "mois": 30}[unit])
    return None

def parse_listing(html, listing_url, collecte_le=None): # Extraire les offres d'une page de resultats. Champs absents -> None. Retourne (offres, nb_cartes_ignorees).
    soup        = BeautifulSoup(html, "html.parser")
    collecte_le = collecte_le or datetime.now(timezone.utc).isoformat()
    today       = datetime.fromisoformat(collecte_le).date()
    offers, ignored = [], 0
    for rank, li in enumerate(soup.find_all("li"), start=1):
        h2 = li.find("h2")
        if h2 is None or li.find("li") is not None:
            continue
        titre = h2.get_text(" ", strip=True) or None
        lines = [_clean(x) for x in li.get_text("\n").split("\n")]
        lines = [x for x in lines if x and x.lower() not in NOISE]
        try:
            start = next(i for i, x in enumerate(lines) if x == titre) + 1
        except StopIteration:
            start = 0
        company, localisation, loc_idx = None, None, None
        for i in range(start, len(lines)):
            m = LOC_RE.match(lines[i])
            if m:
                loc_idx = i
                localisation = f"{m.group('dept')} - {m.group('city').strip()}"
                company = m.group("company")
                break
        if loc_idx is not None and company is None:
            before = [x for x in lines[start:loc_idx] if x]
            company = " ".join(before) or None
        contrat = next((x for x in lines[(loc_idx or start):] if x.lower() in CONTRACTS), None)
        pub = next((x for x in lines if x.lower().startswith("publié")), None)
        a = li.find("a", href=DETAIL_RE)
        m = DETAIL_RE.search(a["href"]) if a else None
        if not titre:
            ignored += 1
            continue
        if m:
            url, oid = f"{FT_BASE}/offres/recherche/detail/{m.group(1)}", f"ft-{m.group(1)}"
        else:
            url, oid = f"{listing_url}#rang-{rank}", f"ft-{hashlib.sha1(listing_url.encode()).hexdigest()[:8]}-{rank}"
        pub_date = parse_published(pub, today)
        offers.append({
            "offre_id": oid, "titre": titre, "entreprise": company, "localisation": localisation,
            "contrat": contrat, "date_publication": pub_date.isoformat() if pub_date else None,
            "url_source": url, "page_source": listing_url, "source": "francetravail",
            "collecte_le": collecte_le, "url_fiable": bool(m),
        })
    return offers, ignored

def collect(listing_urls=None, max_pages=None, session=None, robots=None):
    listing_urls = (listing_urls or FT_LISTING_URLS)[: (max_pages or FT_MAX_PAGES)]
    stats = {"pages_demandees": len(listing_urls), "pages_lues": 0, "refus_robots": 0, "erreurs_http": 0,
             "cartes_ignorees": 0, "sans_url_fiche": 0, "arret_anti_bot": False, "offres": 0}
    try:
        robots = robots or Robots(f"{FT_BASE}/robots.txt")
    except Exception as exc:
        log.error("robots.txt illisible (%s) : collecte France Travail annulee par prudence.", exc)
        stats["erreurs_http"] += 1
        return [], stats
    sess = session or PoliteSession()
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for url in listing_urls:
        if not robots.allowed(url):
            log.warning("Interdit par robots.txt : %s", url)
            stats["refus_robots"] += 1
            continue
        r = sess.get(url)
        if r.status_code in (401, 403, 429) or "captcha" in r.text[:5000].lower():
            log.error("HTTP %s / captcha sur %s : arret, aucun contournement.", r.status_code, url)
            stats["arret_anti_bot"] = True
            break
        if r.status_code != 200:
            stats["erreurs_http"] += 1
            continue
        stats["pages_lues"] += 1
        if FT_SAVE_HTML:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_DIR / (re.sub(r"\W+", "_", url.split("//", 1)[1]) + ".html")).write_text(r.text, encoding="utf-8")
        offers, ignored = parse_listing(r.text, url, now)
        stats["cartes_ignorees"] += ignored
        stats["sans_url_fiche"] += sum(1 for o in offers if not o["url_fiable"])
        out.extend(offers)
    stats["offres"] = len(out)
    return out, stats
