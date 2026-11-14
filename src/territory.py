"""Utilitaires territoriaux sans appel reseau (hierarchie Adzuna `location.area`)."""
from config  import HDF_DEPARTEMENTS, HDF_REGION_ALIASES
from filters import strip_accents

def _n(x):
    return " ".join(strip_accents((x or "").lower()).replace("-", " ").replace("'", " ").split())

DEPT_BY_NAME = {_n(v): k for k, v in HDF_DEPARTEMENTS.items()}
_NON_COMMUNE = set(DEPT_BY_NAME) | HDF_REGION_ALIASES | {"france"}

def in_hdf(area):
    names = {_n(a) for a in (area or [])}
    return bool(names & HDF_REGION_ALIASES) or bool(names & set(DEPT_BY_NAME))

def dept_of(area):
    """(code, nom) du departement HdF present dans la hierarchie, sinon (None, None)."""
    for a in area or []:
        if _n(a) in DEPT_BY_NAME:
            return DEPT_BY_NAME[_n(a)], a
    return None, None

def commune_of(area):
    """Dernier niveau de la hierarchie s'il s'agit d'une commune (ni pays, ni region, ni departement)."""
    if not area or len(area) < 2:
        return None
    last = area[-1]
    return None if _n(last) in _NON_COMMUNE else last

def is_area_label(label):
    """Vrai si le libelle designe un pays, une region ou un departement (et non une commune)."""
    return _n(label) in _NON_COMMUNE