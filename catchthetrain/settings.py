"""The setup wizard's questions and the /settings summary.

Answers are parsed into a draft dict in Profile's JSON form, so a finished draft
becomes a Profile via Profile.from_json.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Callable

from .profile import fmt_days, parse_days, parse_minutes, parse_window
from .stations import parse_stations, station_name
from .timeparse import fmt_t

MAX_HOME_STATIONS = 3  # each one is another BART lookup per plan


@dataclass(frozen=True)
class Field:
    key: str
    label: str  # settings button and summary label
    ask: Callable[[dict], str]  # draft -> question
    parse: Callable[[str, dict], dict]  # answer, draft -> draft updates; ValueError explains a bad answer
    show: Callable[[dict], str]  # draft -> current value
    suggest: tuple[str, ...] = ()  # one-tap answers
    has: Callable[[dict], bool] | None = None  # whether the draft already has a value; default: key present

    def known(self, draft: dict) -> bool:
        return self.has(draft) if self.has else self.key in draft


def _names(codes) -> str:
    return ", ".join(station_name(c) for c in codes)


def _parse_home(text: str, d: dict) -> dict:
    codes = parse_stations(text)
    if len(codes) > MAX_HOME_STATIONS:
        raise ValueError(f"Pick at most {MAX_HOME_STATIONS} stations.")
    if d.get("office") in codes:
        raise ValueError(f"{station_name(d['office'])} is your office station.")
    return {"home": codes}


def _parse_office(text: str, d: dict) -> dict:
    codes = parse_stations(text)
    if len(codes) != 1:
        raise ValueError("Send just one station.")
    if codes[0] in d.get("home", []):
        raise ValueError(f"{station_name(codes[0])} is one of your home stations.")
    return {"office": codes[0]}


def _ask_drive(d: dict) -> str:
    home = d["home"]
    if len(home) == 1:
        return f"🚗 How many minutes is the drive from home to {station_name(home[0])}?"
    example = ", ".join(["12", "18", "25"][:len(home)])
    return f"🚗 How many minutes is the drive from home to {_names(home)}? Reply in that order, e.g. {example}"


def _parse_drive(text: str, d: dict) -> dict:
    home = d["home"]
    parts = text.replace(",", " ").split()
    if len(parts) != len(home):
        raise ValueError("Send a number of minutes." if len(home) == 1 else f"Send {len(home)} numbers, one per station.")
    return {"drive": dict(zip(home, (parse_minutes(p) for p in parts)))}


def _minutes(key: str, label: str, question: str, suggest: tuple[str, ...]) -> Field:
    return Field(key, label, lambda d: question, lambda t, d: {key: parse_minutes(t)},
                 lambda d: f"{d[key]} min", suggest)


def _window(key: str, label: str, question: str, pm_if_bare: bool) -> Field:
    return Field(key, label, lambda d: question, lambda t, d: {key: parse_window(t, pm_if_bare)},
                 lambda d: "–".join(fmt_t(time.fromisoformat(x)) for x in d[key]))


FIELDS = {f.key: f for f in (
    Field("home", "Home stations",
          lambda d: "🏠 Which BART station(s) do you drive to from home?\n"
                    "Send a name or code, e.g. Union City or UCTY. Up to 3: UCTY, WARM",
          _parse_home, lambda d: _names(d["home"])),
    Field("office", "Office station", lambda d: "🏢 Which BART station is closest to your office?",
          _parse_office, lambda d: station_name(d["office"])),
    Field("drive", "Drive times", _ask_drive, _parse_drive,
          lambda d: ", ".join(f"{station_name(s)} {m} min" for s, m in d["drive"].items()),
          has=lambda d: bool(d.get("home")) and set(d.get("drive", {})) == set(d["home"])),
    _minutes("park_walk", "Walk from parking", "🚶 How many minutes from where you park to the platform?",
             ("3", "5", "7")),
    _minutes("office_walk", "Walk to office", "🚶 How many minutes between the platform and your office?",
             ("5", "10", "15")),
    Field("days", "Commute days",
          lambda d: "📅 Which days do you go to the office?\nFor example: tue, or tue,thu, or mon-fri",
          lambda t, d: {"days": parse_days(t)}, lambda d: fmt_days(d["days"]), ("mon-fri",)),
    _window("morning", "Morning alerts",
            "⏰ Morning alerts: between what times might you leave home? e.g. 7:30-9:30", False),
    _window("evening", "Evening alerts",
            "⏰ Evening alerts: between what times might you leave the office? e.g. 5-6:30 (PM assumed)", True),
    _minutes("buffer", "Buffer", "⏱ How many spare minutes do you want before the train (parking, fare gates)?",
             ("0", "3", "5")),
    _minutes("lead", "Alert lead", "🔔 How many minutes before leave time should I alert you?", ("5", "10", "15")),
)}

SETUP_STEPS = ["home", "office", "drive", "park_walk", "office_walk", "days", "morning", "evening"]
# Changing home stations needs a drive time for each new one.
EDIT_STEPS = {"home": ["home", "drive"]}


def summary(d: dict) -> str:
    return "\n".join(f"• {f.label}: {f.show(d)}" for f in FIELDS.values())
