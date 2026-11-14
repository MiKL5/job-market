"""Orchestrateur ETL : Extract (France Travail + Adzuna) -> Transform -> Enrich (Adzuna) -> Load (PostgreSQL/SQLite)."""
import argparse
import json
import logging
import sys
import adzuna
import francetravail
from   config    import DB_BACKEND
from   enrich    import resolve
from   load      import DbConfigError, existing_content_keys, load, open_db, run_checks
from   normalize import content_key, normalize_city

try:
    from rich.console import Console
    from rich.table   import Table
except ImportError:      # Rich est optionnel et repli sur print()
    Console = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pipeline")

def transform(raw):
    """Nettoyage, valeurs manquantes, dedoublonnage dans l'execution. Cle naturelle = identifiant source ;
    cle de contenu (titre + entreprise + ville normalises) pour les doublons inter-sources."""
    clean, seen_id, seen_content, missing, dup_id, dup_content = [], set(), set(), 0, 0, 0
    for o in raw:
        titre = " ".join((o.get("titre") or "").split())
        if not titre or not o.get("url_source"):
            missing += 1
            continue
        o["titre"] = titre
        o["entreprise"] = " ".join(o["entreprise"].split()) if o.get("entreprise") else None
        o["ville_normalisee"] = normalize_city(o.get("localisation"))
        ck = content_key(titre, o["entreprise"], o["ville_normalisee"])
        o["offre_id"] = o.get("offre_id") or "x-" + ck[:16]
        if o["offre_id"] in seen_id:
            dup_id += 1
            continue
        if ck in seen_content:
            dup_content += 1
            continue
        seen_id.add(o["offre_id"])
        seen_content.add(ck)
        clean.append(o)
    return clean, {"extraites": len(raw), "rejetees_champs_manquants": missing,
                   "doublons_identifiant": dup_id, "doublons_contenu": dup_content,
                   "doublons_total": dup_id + dup_content, "finales": len(clean)}

def drop_known_duplicates(offres, known):
    """Ecarte les offres dont le contenu existe deja en base sous un AUTRE identifiant (autre source ou autre run).
    Une offre deja stockee sous le meme identifiant est conservee : elle sera mise a jour (upsert)."""
    kept, dup = [], 0
    for o in offres:
        owner = known.get(content_key(o["titre"], o["entreprise"], o["ville_normalisee"]))
        if owner and owner != o["offre_id"]:
            dup += 1
            continue
        kept.append(o)
    return kept, dup

def enrich(offres, fetch=None):
    cache, communes, rejets = {}, {}, []
    for o in offres:
        statut, commune, detail = resolve(o.get("localisation"), cache, fetch)
        o["statut"], o["commune_id"] = statut, None
        if statut == "apparie":
            o["commune_id"] = commune["commune_id"]
            communes[commune["commune_id"]] = commune
        else:
            rejets.append({"offre_id": o["offre_id"], "localisation": o.get("localisation"),
                           "ville": o["ville_normalisee"], "statut": statut, "detail": detail})
    return list(communes.values()), rejets

def run(skip_ft=False, skip_adzuna=False, backend=None, sqlite_path=None, fetch=None):
    # La base est ouverte EN PREMIER : si Docker n'est pas pret, on echoue avant de scraper.
    with open_db(backend, sqlite_path) as db:
        ft, ft_stats = ([], {"ignore": True}) if skip_ft else francetravail.collect()
        az, az_stats = ([], {"ignore": True}) if skip_adzuna else adzuna.collect()
        offres, t_stats = transform(ft + az)
        offres, dup_base = drop_known_duplicates(offres, existing_content_keys(db))
        t_stats["doublons_deja_en_base"] = dup_base
        t_stats["doublons_total"] += dup_base
        t_stats["finales"] = len(offres)
        communes, rejets = enrich(offres, fetch)
        for o in offres:
            o.setdefault("contrat", None)
            o.setdefault("page_source", None)
            o.setdefault("date_publication", None)
        apparies = sum(1 for o in offres if o["statut"] == "apparie")
        load(db, communes, offres, rejets)
        checks = run_checks(db)
        dialect = db.dialect
    return {
        "backend": dialect, "francetravail": ft_stats, "adzuna": az_stats, "transformation": t_stats,
        "enrichissement": {"apparies": apparies, "non_apparies": sum(1 for r in rejets if r["statut"] == "non_trouve"),
                           "ambigus": sum(1 for r in rejets if r["statut"] == "ambigu"),
                           "erreurs": sum(1 for r in rejets if r["statut"] == "erreur"),
                           "taux": round(apparies / len(offres), 3) if offres else None,
                           "exemples_non_apparies": rejets[:5]},
        "controles_sql": checks,
    }

def display(report):
    if Console is None:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    c = Console()
    c.rule(f"[bold]Rapport ETL ({report['backend']})[/bold]")
    t = Table(title="Volumes et qualite")
    t.add_column("Indicateur"); t.add_column("Valeur", justify="right")
    tr, en = report["transformation"], report["enrichissement"]
    for k, v in [("Lignes extraites", tr["extraites"]), ("Rejetees (champs manquants)", tr["rejetees_champs_manquants"]),
                 ("Doublons dans l'execution (id + contenu)", tr["doublons_identifiant"] + tr["doublons_contenu"]),
                 ("Doublons deja en base (autre source/run)", tr.get("doublons_deja_en_base", 0)),
                 ("Lignes finales", tr["finales"]),
                 ("Offres rapprochees a une commune", en["apparies"]), ("Non appariees", en["non_apparies"]),
                 ("Ambigues", en["ambigus"]), ("Erreurs API", en["erreurs"]), ("Taux d'enrichissement", en["taux"]),
                 ("SELECT COUNT(*) FROM offres (table entiere)", report["controles_sql"]["count"][0]["nb_offres"])]:
        t.add_row(str(k), str(v))
    c.print(t)
    for name in ("par_departement", "par_entreprise", "par_source_statut"):
        rows = report["controles_sql"][name]
        if not rows:
            c.print(f"[yellow]{name} : aucune ligne[/yellow]")
            continue
        tab = Table(title=name)
        for col in rows[0]:
            tab.add_column(col)
        for r in rows:
            tab.add_row(*[str(x) for x in r.values()])
        c.print(tab)
    if en["exemples_non_apparies"]:
        c.print("[bold]Exemples non apparies / ambigus :[/bold]")
        for r in en["exemples_non_apparies"]:
            c.print(f"  - {r['localisation']!r} -> {r['statut']} ({r['detail']})")
    c.print("Collecte France Travail :", report["francetravail"])
    c.print("Collecte Adzuna :", report["adzuna"])

def main(argv=None):
    ap = argparse.ArgumentParser(description="ETL offres data/IA - Hauts-de-France")
    ap.add_argument("--skip-ft", action="store_true", help="ne pas scraper France Travail")
    ap.add_argument("--skip-adzuna", action="store_true", help="ne pas collecter via Adzuna")
    ap.add_argument("--backend", choices=["postgres", "sqlite"], default=None,
                    help=f"moteur de base (defaut : {DB_BACKEND}, depuis .env)")
    ap.add_argument("--json", action="store_true", help="sortie JSON brute")
    a = ap.parse_args(argv)
    try:
        report = run(a.skip_ft, a.skip_adzuna, backend=a.backend)
    except DbConfigError as exc:
        log.error("%s", exc)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str)) if a.json else display(report)
    return 0

if __name__ == "__main__":
    sys.exit(main())
