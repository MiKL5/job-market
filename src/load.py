import os
import re
import sqlite3
from   contextlib import contextmanager
from   config     import DB_BACKEND, PG, SQLITE_PATH
from   normalize  import content_key


class DbConfigError(RuntimeError):
    pass


DDL = [
    """CREATE TABLE IF NOT EXISTS communes (
        commune_id       TEXT PRIMARY KEY,
        nom              TEXT NOT NULL,
        code_departement TEXT,
        departement      TEXT,
        region           TEXT,
        code_insee       TEXT,
        latitude         DOUBLE PRECISION,
        longitude        DOUBLE PRECISION,
        source           TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS offres (
        offre_id         TEXT PRIMARY KEY,
        titre            TEXT NOT NULL,
        entreprise       TEXT,
        contrat          TEXT,
        localisation_brute TEXT,
        ville_normalisee TEXT,
        commune_id       TEXT REFERENCES communes(commune_id),
        statut_enrichissement TEXT NOT NULL
            CHECK (statut_enrichissement IN ('apparie','ambigu','non_trouve','erreur')),
        url_source       TEXT NOT NULL,
        page_source      TEXT,
        source           TEXT NOT NULL,
        date_publication DATE,
        collecte_le      TIMESTAMP NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS offres_non_appariees (
        offre_id         TEXT PRIMARY KEY,
        localisation_brute TEXT,
        ville_normalisee TEXT,
        statut           TEXT NOT NULL,
        detail           TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_offres_commune ON offres(commune_id)",
    "CREATE INDEX IF NOT EXISTS idx_offres_source ON offres(source)",
]


UPSERT_COMMUNE = """INSERT INTO communes (commune_id, nom, code_departement, departement, region, code_insee,
    latitude, longitude, source) VALUES (:commune_id, :nom, :code_departement, :departement, :region, :code_insee,
    :latitude, :longitude, :source)
    ON CONFLICT (commune_id) DO UPDATE SET nom=excluded.nom, code_departement=excluded.code_departement,
    departement=excluded.departement, region=excluded.region, latitude=excluded.latitude,
    longitude=excluded.longitude"""


UPSERT_OFFRE = """INSERT INTO offres (offre_id, titre, entreprise, contrat, localisation_brute, ville_normalisee,
    commune_id, statut_enrichissement, url_source, page_source, source, date_publication, collecte_le)
    VALUES (:offre_id, :titre, :entreprise, :contrat, :localisation, :ville_normalisee, :commune_id, :statut,
    :url_source, :page_source, :source, :date_publication, :collecte_le)
    ON CONFLICT (offre_id) DO UPDATE SET titre=excluded.titre, entreprise=excluded.entreprise,
    contrat=excluded.contrat, localisation_brute=excluded.localisation_brute,
    ville_normalisee=excluded.ville_normalisee, commune_id=excluded.commune_id,
    statut_enrichissement=excluded.statut_enrichissement, url_source=excluded.url_source,
    page_source=excluded.page_source, date_publication=excluded.date_publication,
    collecte_le=excluded.collecte_le"""


UPSERT_REJET = """INSERT INTO offres_non_appariees (offre_id, localisation_brute, ville_normalisee, statut, detail)
    VALUES (:offre_id, :localisation, :ville, :statut, :detail)
    ON CONFLICT (offre_id) DO UPDATE SET localisation_brute=excluded.localisation_brute,
    ville_normalisee=excluded.ville_normalisee, statut=excluded.statut, detail=excluded.detail"""


CHECKS = {
    "count": "SELECT COUNT(*) AS nb_offres FROM offres",
    "par_departement": """SELECT c.departement, c.code_departement, COUNT(*) AS nb_offres
        FROM offres o JOIN communes c ON c.commune_id = o.commune_id
        GROUP BY c.departement, c.code_departement ORDER BY nb_offres DESC, c.departement""",
    "par_entreprise": """SELECT UPPER(COALESCE(entreprise, '(non renseignee)')) AS entreprise, COUNT(*) AS nb_offres
        FROM offres GROUP BY UPPER(COALESCE(entreprise, '(non renseignee)'))
        ORDER BY nb_offres DESC, entreprise LIMIT 15""",
    "par_source_statut": """SELECT source, statut_enrichissement, COUNT(*) AS nb
        FROM offres GROUP BY source, statut_enrichissement ORDER BY source, statut_enrichissement""",
}


class Db:
    def __init__(self, conn, dialect):
        self.conn, self.dialect = conn, dialect


    def _sql(self, sql):
        return re.sub(r":(\w+)", r"%(\1)s", sql) if self.dialect == "postgresql" else sql


    def execute(self, sql, params=None):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params or {})
        return cur


    def executemany(self, sql, rows):
        if rows:
            cur = self.conn.cursor()
            cur.executemany(self._sql(sql), rows)


def _rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _connect_postgres():
    missing = [k for k in ("user", "password", "dbname") if not PG[k]]
    if missing:
        raise DbConfigError("PostgreSQL : variable(s) manquante(s) dans .env : "
                            + ", ".join("POSTGRES_" + {"dbname": "DB"}.get(k, k.upper()) for k in missing))
    try:
        import psycopg
    except ImportError as exc:
        raise DbConfigError("Le paquet psycopg est absent : pip install -r requirements.txt") from exc
    try:
        return psycopg.connect(user=PG["user"], password=PG["password"], dbname=PG["dbname"],
                               host=PG["host"], port=PG["port"], connect_timeout=5)
    except psycopg.OperationalError as exc:
        msg = str(exc)
        if "password authentication failed" in msg or "does not exist" in msg:
            hint = ("Identifiants refuses : POSTGRES_USER/POSTGRES_PASSWORD de .env ne correspondent pas a ceux utilises "
                    "a la creation du volume Docker (voir 'docker compose down -v' puis 'docker compose up -d').")
        else:
            hint = ("Le conteneur est-il demarre et 'healthy' ? (docker compose up -d --wait ; docker compose ps)")
        raise DbConfigError(f"Connexion PostgreSQL impossible ({PG['host']}:{PG['port']}). {hint} Detail : {msg}") from exc


@contextmanager
def open_db(backend=None, sqlite_path=None):
    backend = (backend or DB_BACKEND).lower()
    if backend in ("postgres", "postgresql"):
        conn, dialect = _connect_postgres(), "postgresql"
    elif backend == "sqlite":
        path = sqlite_path or SQLITE_PATH
        if str(path) != ":memory:":
            os.makedirs(os.path.dirname(str(path)) or ".", exist_ok=True)
        conn, dialect = sqlite3.connect(str(path)), "sqlite"
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        raise DbConfigError(f"DB_BACKEND inconnu : {backend!r} (attendu : postgres ou sqlite)")
    try:
        db = Db(conn, dialect)
        for stmt in DDL:
            db.execute(stmt)
        yield db
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def existing_content_keys(db): # clé naturelle de contenu : titre, entreprise, ville_normalisee
    rows = db.execute("SELECT offre_id, titre, entreprise, ville_normalisee FROM offres").fetchall()
    return {content_key(t, e, v): oid for oid, t, e, v in rows}


def load(db, communes, offres, rejets): # charger les trois tables dans l'ordre, idempotent (upsert sur la cle naturelle)
    db.executemany(UPSERT_COMMUNE, communes)
    db.executemany(UPSERT_OFFRE, offres)
    ids = [o["offre_id"] for o in offres]
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        marks = ",".join(f":i{j}" for j in range(len(chunk)))
        db.execute(f"DELETE FROM offres_non_appariees WHERE offre_id IN ({marks})",
                   {f"i{j}": v for j, v in enumerate(chunk)})
    db.executemany(UPSERT_REJET, rejets)


def run_checks(db):
    return {name: _rows(db.execute(sql)) for name, sql in CHECKS.items()}
