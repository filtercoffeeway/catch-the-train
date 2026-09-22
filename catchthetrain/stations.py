"""BART station catalog and lookup by code or name."""
from __future__ import annotations

import difflib
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
# What typos are compared against: codes, names, name parts and longer words ("berkly" -> "berkeley").
_FUZZY: dict[str, list[str]] = {}
for _code, _parts in _PARTS.items():
    for _key in {_code.lower(), *_parts, *(w for p in _parts for w in p.split() if len(w) >= 4)}:
        _FUZZY.setdefault(_key, []).append(_code)
MAX_FIX_BYTES = 48  # corrected answers ride in Telegram callback data (64-byte limit)


class StationError(ValueError):
    """A station answer that didn't resolve, with corrected answers to offer as one-tap buttons."""

    def __init__(self, msg: str, fixes: list[tuple[str, str]]):
        super().__init__(msg)
        self.fixes = fixes  # (button label, corrected answer)


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


def close_matches(text: str) -> list[str]:
    """Codes of stations whose code or name is spelled close to `text`, best first ("civc center")."""
    q = _norm(text)
    scored = sorted(((difflib.SequenceMatcher(None, q, k).ratio(), k) for k in _FUZZY), reverse=True)
    if not scored or scored[0][0] < 0.75:
        return []
    # Keep only near-ties with the best match, so one clear winner isn't diluted.
    hits = [k for score, k in scored if score >= scored[0][0] - 0.05]
    return list(dict.fromkeys(code for h in hits for code in _FUZZY[h]))[:3]


def _best(part: str) -> str:
    """`part` as a code if it's unambiguous or has a clear close match, else unchanged."""
    hits = find(part)
    if len(hits) == 1:
        return hits[0]
    close = close_matches(part) if not hits else []
    return close[0] if len(close) == 1 else part


def parse_stations(text: str) -> list[str]:
    """'Union City, WARM' -> ['UCTY', 'WARM']. StationError says which part is unknown or ambiguous,
    and offers the whole answer corrected for each likely station."""
    parts: list[str] = []
    for part in re.split(r",|&|\+|\band\b", text):
        words = part.split()
        if len(words) > 1 and all(w.upper() in NAMES for w in words):  # "UCTY WARM"
            parts += words
        elif words:
            parts.append(part.strip())
    if not parts:
        raise ValueError("Send a station name or code, like Union City or UCTY.")
    codes: list[str] = []
    for i, part in enumerate(parts):
        hits = find(part)
        if len(hits) == 1:
            if hits[0] not in codes:
                codes.append(hits[0])
            continue
        if hits:
            options = hits[:6]
            msg = f"“{part}” could be {' or '.join(station_name(c) for c in options)}. Which one?"
        else:
            options = close_matches(part)
            msg = f"I don't know a BART station called “{part}”."
            if options:
                msg += f" Did you mean {' or '.join(station_name(c) for c in options)}?"
        rest = [_best(p) for p in parts[i + 1:]]
        fixes = [(station_name(c), ", ".join([*codes, c, *rest])) for c in options]
        raise StationError(msg, [(label, a) for label, a in fixes if len(a.encode()) <= MAX_FIX_BYTES])
    return codes
