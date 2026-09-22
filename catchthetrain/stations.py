"""BART station catalog and lookup by code or name."""
from __future__ import annotations

import re

NAMES = {
    "12TH": "12th St Oakland City Center", "16TH": "16th St Mission", "19TH": "19th St Oakland",
    "24TH": "24th St Mission", "ANTC": "Antioch", "ASHB": "Ashby", "BALB": "Balboa Park",
    "BAYF": "Bay Fair", "BERY": "Berryessa/North San Jose", "CAST": "Castro Valley",
    "CIVC": "Civic Center/UN Plaza", "COLM": "Colma", "COLS": "Coliseum", "CONC": "Concord",
    "DALY": "Daly City", "DBRK": "Downtown Berkeley", "DELN": "El Cerrito del Norte",
    "DUBL": "Dublin/Pleasanton", "EMBR": "Embarcadero", "FRMT": "Fremont", "FTVL": "Fruitvale",
    "GLEN": "Glen Park", "HAYW": "Hayward", "LAFY": "Lafayette", "LAKE": "Lake Merritt",
    "MCAR": "MacArthur", "MLBR": "Millbrae", "MLPT": "Milpitas", "MONT": "Montgomery St",
    "NBRK": "North Berkeley", "NCON": "North Concord/Martinez", "OAKL": "Oakland International Airport",
    "ORIN": "Orinda", "PCTR": "Pittsburg Center", "PHIL": "Pleasant Hill/Contra Costa Centre",
    "PITT": "Pittsburg/Bay Point", "PLZA": "El Cerrito Plaza", "POWL": "Powell St", "RICH": "Richmond",
    "ROCK": "Rockridge", "SANL": "San Leandro", "SBRN": "San Bruno", "SFIA": "San Francisco International Airport",
    "SHAY": "South Hayward", "SSAN": "South San Francisco", "UCTY": "Union City", "WARM": "Warm Springs/South Fremont",
    "WCRK": "Walnut Creek", "WDUB": "West Dublin/Pleasanton", "WOAK": "West Oakland",
}
ALIASES = {"sfo": "SFIA", "oakland airport": "OAKL"}


def station_name(code: str) -> str:
    return NAMES.get(code, code)


def _norm(s: str) -> str:
    return " ".join(s.lower().replace(".", " ").replace("street", "st").split())


# Each name plus its "/"-separated parts, so "Warm Springs" and "South Fremont" both find WARM.
_PARTS = {code: {_norm(p) for p in [name, *name.split("/")]} for code, name in NAMES.items()}


def find(text: str) -> list[str]:
    """Codes of stations matching a code or name; exactly one entry means a unique match."""
    q = _norm(text)
    if not q:
        return []
    if q.upper() in NAMES:
        return [q.upper()]
    if q in ALIASES:
        return [ALIASES[q]]
    for match in (lambda p: p == q, lambda p: p.startswith(q), lambda p: q in p):
        hits = [code for code, parts in _PARTS.items() if any(match(p) for p in parts)]
        if hits:
            return hits
    return []


def parse_stations(text: str) -> list[str]:
    """'Union City, WARM' -> ['UCTY', 'WARM']. ValueError says which part is unknown or ambiguous."""
    codes: list[str] = []
    for part in re.split(r",|&|\+|\band\b", text):
        if not part.strip():
            continue
        words = part.split()
        if len(words) > 1 and all(w.upper() in NAMES for w in words):  # "UCTY WARM"
            hits_per_part = [[w.upper()] for w in words]
        else:
            hits_per_part = [find(part)]
        for hits in hits_per_part:
            if not hits:
                raise ValueError(f"I don't know a BART station called “{part.strip()}”.")
            if len(hits) > 1:
                options = ", ".join(f"{station_name(c)} ({c})" for c in hits[:6])
                raise ValueError(f"“{part.strip()}” could be {options}. Which one?")
            if hits[0] not in codes:
                codes.append(hits[0])
    if not codes:
        raise ValueError("Send a station name or code, like Union City or UCTY.")
    return codes
