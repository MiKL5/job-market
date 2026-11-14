import logging
import time
import requests
from   datetime  import datetime, timezone
from   config    import (ADZUNA_DELAY_S, ADZUNA_ID, ADZUNA_KEY, ADZUNA_MAX_PAGES, ADZUNA_WHERE, TIMEOUT_S, USER_AGENT)
from   filters   import title_matches
from   territory import in_hdf

log = logging.getLogger(__name__)
BASE = "https://api.adzuna.com/v1/api/jobs/fr"
QUERIES = ["data alternance", "data alternant", "data stage", "ia alternance", "ia stage",
           "intelligence artificielle alternance", "intelligence artificielle stage"]

def adzuna_get(path, params):
    # GET JSON avec nouvelles tentatives (reseau, 429, 5xx). Retourne None en cas d'echec definitif.
    if not ADZUNA_ID or not ADZUNA_KEY:
        log.error("ADZUNA_APP_ID / ADZUNA_APP_KEY absents : renseigne le fichier .env")
        return None
    p = {"app_id": ADZUNA_ID, "app_key": ADZUNA_KEY, **params}
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE}/{path}", params=p, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
        except requests.RequestException as exc:
            log.warning("Adzuna reseau : %s", exc)
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                log.error("Adzuna : reponse non JSON")
                return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 2)
            continue
        log.error("Adzuna HTTP %s : %s", r.status_code, r.text[:200])
        return None
    return None

def collect(queries=None, wheres=None, max_pages=None, delay=None):
    now = datetime.now(timezone.utc).isoformat()
    delay = ADZUNA_DELAY_S if delay is None else delay
    offers, stats = [], {"appels": 0, "appels_en_echec": 0, "resultats_bruts": 0, "hors_region": 0,
                         "hors_filtre": 0, "sans_url": 0}
    for where in (wheres or ADZUNA_WHERE):
        for q in (queries or QUERIES):
            for page in range(1, (max_pages or ADZUNA_MAX_PAGES) + 1):
                data = adzuna_get(f"search/{page}", {"what": q, "where": where, "results_per_page": 50, "sort_by": "date"})
                stats["appels"] += 1
                time.sleep(delay)
                if data is None:
                    stats["appels_en_echec"] += 1
                    break
                results = data.get("results") or []
                if not results:
                    break
                for it in results:
                    stats["resultats_bruts"] += 1
                    area = (it.get("location") or {}).get("area") or []
                    if not in_hdf(area):
                        stats["hors_region"] += 1
                        continue
                    if not title_matches(it.get("title")):
                        stats["hors_filtre"] += 1
                        continue
                    if not it.get("redirect_url"):
                        stats["sans_url"] += 1
                        continue
                    offers.append({
                        "offre_id": f"az-{it.get('id')}" if it.get("id") else None,
                        "titre": it.get("title"),
                        "entreprise": (it.get("company") or {}).get("display_name"),
                        "localisation": (it.get("location") or {}).get("display_name"),
                        "contrat": it.get("contract_time") or it.get("contract_type"),
                        "date_publication": (it.get("created") or "")[:10] or None,
                        "url_source": it["redirect_url"], "page_source": f"adzuna:search?what={q}&where={where}",
                        "source": "adzuna", "collecte_le": now, "url_fiable": True,
                    })
    stats["offres"] = len(offers)
    return offers, stats

if __name__ == "__main__":
    # Sonde de validation : affiche la forme reelle de location.area (a lire avant le premier run complet)
    import json
    d = adzuna_get("search/1", {"what": "data", "where": "Lille", "results_per_page": 3})
    print(json.dumps([{"title": r.get("title"), "location": r.get("location"), "id": r.get("id")}
                      for r in (d or {}).get("results", [])], indent=2, ensure_ascii=False))
