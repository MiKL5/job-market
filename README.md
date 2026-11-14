# JobMarket

<div align="center">

![Python](https://img.shields.io/badge/Python-3.14.7-3776AB?logo=python&logoColor=white) ![Requests](https://img.shields.io/badge/Requests-HTTP-2C5BB4) ![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup4-html.parser-green) ![Adzuna](https://img.shields.io/badge/API-Adzuna-orange)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18.6-4169E1?logo=postgresql&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white) ![Rich](https://img.shields.io/badge/Rich-terminal-purple) ![RGPD](https://img.shields.io/badge/RGPD-minimisation-blue)

</div>

Ce pipeline ETL étudie la répartition territoriale d'offres d'emploi et de stage/alternance en Data et IA :
* **Extract** : scraping HTML de France Travail (`requests` + `BeautifulSoup`, sans framework de scraping) et collecte par l'API Adzuna ;
* **Transform** : nettoyage des textes, traitement des doublons et des valeurs manquantes, normalisation des villes ;
* **Enrich** : rattachement de chaque offre à une commune par l'API Adzuna, avec règle explicite contre les homonymes ;
* **Load** : chargement dans PostgreSQL 18.6 (Docker), avec tables `offres`, `communes` et `offres_non_appariees`.
---
## Les prérequis
* Exécuté sous Python 3.14.7 ;
* Docker avec Docker Compose ;
* obtenir de l'api `app_id` et `app_key` via un compte Adzuna ;
## L'installation
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # puis renseigner les valeurs ci-dessous
```
Variables du fichier `.env` (jamais versionné) :
Variables | Rôle
---|---
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` | Connexion PostgreSQL aussi utilisées par `docker-compose.yml`
`ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Clés de l'API Adzuna
`CONTACT_EMAIL` | Adresse placée dans le `User-Agent` des requêtes
`FT_MAX_PAGES`, `REQUEST_DELAY_S` | Nombre maximal de pages France Travail et délai entre requêtes (3 s minimum)
`DB_BACKEND` | `postgres` (défaut) ou `sqlite`
## Sources et conditions d'accès
J'ai choisi PostgreSQL parce que je l'ai déjà utilisé dans le passer et surtout ça me permet de continuer de continuer à apprendre Docker.
### Ce qui est scraper en html
Élément | Détail
---|---
L'URL | https://candidat.francetravail.fr (page d'entrée : `/rechercheoffre/emploi`)
Les pages lues | Deux pages de résultats « métier + ville » : `/offres/emploi/data-analyst/lille/s28m18v10` (31 offres annoncées) et `/offres/emploi/data-scientist/lille/s28m15v10` (17 offres annoncées)
Les type d'offres | Offres publiques, tous contrats, secteur Informatique et télécoms
Les champs disponibles | titre, entreprise, localisation (`59 - Lille`), contrat, date de publication relative, URL de la fiche
Les conditions d'accès | les CGU dates du 19/02/2024 et permettent de : <br>consulter des offres sans création de compte ;<br>aucune clause interdisant le moissonnage relevée.<br>Le `robots.txt` est interrogé avant chaque URL ; il interdit notamment le paramètre `motsCles=`, je ne fais pas recherche par mot-clé
Politesse | Le `User-Agent` identifiable avec contact, délai d'au moins 3 s entre requêtes, 10 pages au maximum, arrêt en cas d'erreur HTTP 401/403/429 ou de captcha
Ce qui n'est pas fait | Pas de Selenium, pas de compte, pas de contournement d'authentification, de captcha ou de limite technique ; pas de collecte de coordonnées ni de noms de recruteurs
La pertinence | C'est un jeu de données public, réel, géolocalisé par commune, directement lié à la question territoriale posée
### Ce que je fais avec l'api d'Adzuna
`GET https://api.adzuna.com/v1/api/jobs/fr/search/{page}` avec les paramètres `app_id`, `app_key`, `what`, `where`, `results_per_page`, `sort_by` ([documentation](https://developer.adzuna.com/docs/search)). Le pays (`fr`) et la page sont dans le chemin.
* **Ciblage** : sept requêtes (data/IA/intelligence artificielle combinés à alternance/alternant/stage), `where=Hauts-de-France`, puis filtre strict côté code sur l'intitulé ;
* **Hiérarchie territoriale** : `location.area` renvoie par exemple `France > Hauts-De-France > Nord > Lille > Villeneuve-d'Ascq` ; le dernier niveau est la commune ;
* **Erreurs** : trois tentatives sur erreur réseau, 429 et 5xx ; un échec définitif est compté (`appels_en_echec`) sans interrompre le pipeline ;
* **Choix de l'enseignant** : Adzuna est utilisée à la place de l'API Géo.
## Commandes d'exécution
**Démarrer la base (une fois)**
```bash
docker compose up -d --wait  # démarre PostgreSQL et attend et attend qu'il soit prêt
python src/pipeline.py       # Lancer le pipeline complet
docker exec -i jobmarket_db psql -U job-market -d jobmarket < sql/analytics.sql # Contrôler le contenu de la base
```
**Pour repartir d'une base vide**
```bash
docker exec -it jobmarket_db psql -U job-market -d jobmarket -c "TRUNCATE offres_non_appariees, offres, communes;"
python src/pipeline.py
```
## Structure des donénes
Il y a **3 tables PostgreSQL** (créées par `load.py`) :
Table | Colonnes principales
---|---
Les `communes` | `commune_id` (clé primaire, ex. `59-lille`), `nom`, `code_departement`, `departement`, `region`, `code_insee` (NULL), `latitude`, `longitude`, `source`
Les `offres` | `offre_id` (clé primaire : `ft-<id fiche>` ou `az-<id>`), `titre`, `entreprise`, `contrat`, `localisation_brute`, `ville_normalisee`, `commune_id` (clé étrangère), `statut_enrichissement` (contrainte : apparie / ambigu / non_trouve / erreur), `url_source`, `page_source`, `source`, `date_publication`, `collecte_le`
Les `offres_non_appariees` | `offre_id` (clé primaire), `localisation_brute`, `ville_normalisee`, `statut`, `detail`

**Provenance** : chaque offre conserve sa source, l'URL de la fiche ou de l'annonce, la page de résultats ou la requête d'origine, et l'horodatage de collecte.

**Éviter les doublons au rechargement** : insertion par `ON CONFLICT (offre_id) DO UPDATE` ; l'identifiant est celui de la source, donc une relance met à jour les lignes existantes sans en créer.
## Structure du projet
```
jobMarket/
├── requirements.txt          # dépendances Python
├── docker-compose.yml        # PostgreSQL 18.6 dans le conteneur jobmarket_db
├── .env                      # secrets et paramètres locaux (non versionné)
├── .env.example              # modèle du .env
├── .gitignore
├── data/
│   └── raw/                  # pages HTML brutes de France Travail
├── sql/
│   └── analytics.sql         # requêtes de contrôle (COUNT, GROUP BY, doublons)
├── src/
│   ├── config.py             # paramètres et lecture du fichier .env
│   ├── polite_http.py        # session HTTP et politesse (délai, User-Agent)
│   ├── robots.py             # lecture et respect du robots.txt
│   ├── filters.py            # filtre d'intitulé (data/IA + alternance/stage)
│   ├── normalize.py          # normalisation des villese et clé de dédoublonnage
│   ├── territory.py          # hiérarchie territoriale Adzuna (région, département, commune)
│   ├── francetravail.py      # scraping par requests et BeautifulSoup
│   ├── adzuna.py             # extraction par l'API d'Adzuna
│   ├── enrich.py             # enrichissement territorial et règle anti-homonymes
│   ├── load.py               # chargement PostgreSQL et requêtes de contrôle
│   └── pipeline.py           # orchestration et rapport Rich
└── README.md
```
## Règles de transformation
**Doublons**
1. Même identifiant source : doublon, première occurrence conservée.
2. Même contenu (titre, entreprise et ville normalisés, sans casse ni accents) : doublon, y compris entre sources ; France Travail passe avant Adzuna.
3. Même contenu déjà présent en base sous un autre identifiant (autre source ou autre exécution) : écarté.

**Valeurs manquantes** : une offre sans titre ou sans URL est rejetée et comptée ; entreprise, contrat et date absents restent `NULL`.

**Normalisation de la ville** : accents, casse, « St » en « saint », préfixe de département, code postal, arrondissement et suffixe retirés.

**Règle de rapprochement (aucune correspondance arbitraire)**
1. Une localisation de niveau département ou région (ex. `Nord, Hauts-De-France`) ne désigne aucune commune : `non_trouve`, sans appel API.
2. Sinon, appel Adzuna avec `where=<ville>` ; on garde les résultats situés en Hauts-de-France dont la commune normalisée est égale à la ville.
3. **apparie** : un seul couple (département, commune), ou plusieurs couples dont un seul est compatible avec le département indiqué par la localisation.
4. **ambigu** : plusieurs couples sans indice décisif (villes homonymes) : aucune commune n'est choisie, le cas est tracé.
5. **non_trouve** : aucune commune correspondante ; **erreur** : échec HTTP.

Les offres non appariées ou ambiguës sont conservées dans `offres_non_appariees` avec le motif.

## Limites et décisions techniques
* **La limite est de 20 offres par page France Travail (Selenium n'est pas explicitement autorisé et comme j'ai pas poser la question de savoir si je peux je fais sans).**
* **Adzuna Pas de code INSEE.**  
L'identifiant géographique est `commune_id` accompagné de la latitude et de la longitude.
* **Couverture communale d'Adzuna.**  
Une commune n'apparaît que si Adzuna y recense des annonces.
* **Localisation départementale.**  
Six offres Adzuna du Nord et une du Pas-de-Calais n'ont pas de commune ; tracées mais pas rattachées.
* **Pas de filtre alternance/stage côté France Travail.**  mais Adzuna le permet.
* **Structure HTML**  
L'extraction repose sur la structure actuelle des pages (cartes d'offres en liste, intitulé, ligne entreprise et lieu). Un changement du site peut la casser ; les pages brutes de `data/raw/` permettent de le vérifier.
* **Données du jour.** Les offres évoluent les peuvent changés tous les jours.

**Décisions techniques**
* `requests` + `BeautifulSoup` avec l'analyseur intégré `html.parser` (aucune dépendance supplémentaire).
* PostgreSQL 18.6 via Docker (volume monté sur `/var/lib/postgresql`, comme l'impose l'image 18).
* La base est ouverte avant toute collecte : si Docker n'est pas prêt, le programme s'arrête.

Cadre juridique et éthique
* **RGPD** : aucune donnée nominative collectée, aucun contact de recruteur, minimisation des champs, finalité pédagogique.
* **Droit des bases de données** : volume très limité, pas d'extraction substantielle ni systématique.
* **Respect du site** : `robots.txt` contrôlé, `User-Agent` explicite, délai entre requêtes, arrêt sur blocage.