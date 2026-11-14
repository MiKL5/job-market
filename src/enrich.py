import logging
from   adzuna    import adzuna_get
from   config    import REGION
from   normalize import clean_city_label, extract_hints, normalize_city
from   territory import commune_of, dept_of, is_area_label

log = logging.getLogger(__name__)

def _slug(dept_code, name):
    return f"{dept_code or 'xx'}-{normalize_city(name)}".replace(" ", "-")

def candidates_from_results(items, city_norm):
    found = {}
    for it in items:
        loc     = it.get("location") or {}
        area    = loc.get("area") or []
        commune = commune_of(area)
        if not commune or normalize_city(commune) != city_norm:
            continue
        code, dept = dept_of(area)
        if code is None:          # hors Hauts-de-France
            continue
        found.setdefault((code, dept, commune), {"lat": it.get("latitude"), "lon": it.get("longitude")})
    return found

def resolve(raw_location, cache, fetch=None):
    # Retourne (statut, commune_dict|None, detail)
    fetch = fetch or adzuna_get
    city = normalize_city(raw_location)
    if not city:
        return "non_trouve", None, "localisation vide"
    if is_area_label(clean_city_label(raw_location)):
        return "non_trouve", None, "localisation de niveau departement/region (pas de commune)"
    _, dept_hint = extract_hints(raw_location)
    if city not in cache:
        data = fetch("search/1", {"where": clean_city_label(raw_location), "results_per_page": 50})
        cache[city] = None if data is None else candidates_from_results(data.get("results") or [], city)
    cands = cache[city]
    if cands is None:
        return "erreur", None, "echec HTTP Adzuna"
    if not cands:
        return "non_trouve", None, "aucune commune HdF correspondante dans Adzuna"
    keys = list(cands)
    if len(keys) > 1 and dept_hint:
        narrowed = [k for k in keys if k[0] == dept_hint]
        if len(narrowed) == 1:
            keys = narrowed
    if len(keys) != 1:
        return "ambigu", None, "; ".join(f"{k[0]}-{k[2]}" for k in keys)
    code, dept, commune = keys[0]
    if dept_hint and dept_hint != code:
        return "ambigu", None, f"departement indique {dept_hint} != Adzuna {code}"
    return "apparie", {
        "commune_id": _slug(code, commune), "nom": commune, "code_departement": code, "departement": dept,
        "region": REGION, "code_insee": None, "latitude": cands[keys[0]]["lat"],
        "longitude": cands[keys[0]]["lon"], "source": "adzuna",
    }, ""
