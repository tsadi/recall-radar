"""Common recall record and the topic / severity classifier."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Recall:
    source: str            # CPSC, NHTSA, SafetyGate
    id: str
    date: str              # ISO date (YYYY-MM-DD)
    title: str
    hazard: str = ""
    description: str = ""
    remedy: str = ""
    manufacturer: str = ""
    country: str = ""
    units: Optional[int] = None
    url: str = ""
    flags: list = field(default_factory=list)   # e.g. ["do_not_drive", "fire_when_parked"]
    topics: list = field(default_factory=list)
    score: int = 0

    def text(self) -> str:
        return " ".join([self.title, self.hazard, self.description]).lower()

    def to_dict(self) -> dict:
        return asdict(self)


# Topic -> keyword patterns. Order matters only for display.
TOPICS = {
    "battery": r"lithium|li-ion|lithium-ion|battery|batteries|battery pack|power bank|thermal runaway",
    "energy-storage": r"energy storage|bess|home battery|powerwall|storage system|inverter|solar",
    # word boundaries keep "rechargeable" from counting as a charger recall
    "charging": r"\bchargers?\b|\bcharging (?:station|cable|cord|dock|base|case|pad|adapter|equipment|system)s?\b"
                r"|\bpower suppl(?:y|ies)\b|\b(?:power|ac|wall) adapters?\b",
    "ev-charging": r"\bevse\b|\bev chargers?\b|electric vehicle (?:supply equipment|charg)|charging station"
                   r"|\bwallbox\b|level 2 charg|dc fast charg",
    "e-mobility": r"e-bike|ebike|electric bicycle|e-scooter|scooter|hoverboard|self-balancing|electric unicycle",
    "ev-traction": r"high voltage battery|high-voltage battery|traction battery|hybrid battery|electric vehicle|\bev\b|propulsion",
    "robotics": r"robot|robotic|autonomous|automated driving|self-driving|lawn mower robot|vacuum robot",
}

FIRE = r"fire|burn|overheat|explo|smoke|ignit|thermal runaway|melt"
SEVERE = r"death|died|fatal|serious injur|hospital"
# Physical safety hazards. Recalls with none of these (e.g. RoHS / REACH
# chemical-content withdrawals) are dropped: they are not product safety stories.
SAFETY = FIRE + r"|shock|electrocut|injur|laceration|crash|fall|entrap|pinch|strangul|choking|collision|loss of (?:control|steering|braking|motive power)"


def classify(r: Recall, extra_topics: Optional[dict] = None) -> Recall:
    text = r.text()
    patterns = dict(TOPICS)
    if extra_topics:
        patterns.update(extra_topics)
    r.topics = [name for name, pat in patterns.items() if re.search(pat, text)]
    score = 0
    if re.search(FIRE, text):
        score += 3
        if "fire" not in r.flags:
            r.flags.append("fire")
    if re.search(SEVERE, text):
        score += 4
    if "do_not_drive" in r.flags or "fire_when_parked" in r.flags:
        score += 4
    if r.units:
        score += 3 if r.units >= 100_000 else 2 if r.units >= 10_000 else 1 if r.units >= 1_000 else 0
    score += min(len(r.topics), 2)
    r.score = score
    return r


# Which standards a reader would reach for first, by topic.
STANDARD_HINTS = {
    "battery": "UL 2054 / IEC 62133-2 (portable packs), UL 2056 (power banks), UN 38.3",
    "energy-storage": "UL 9540 / UL 9540A, UL 1973, UL 1741, NFPA 855",
    "charging": "UL 1310 / IEC 62368-1 (chargers and power supplies)",
    "ev-charging": "UL 2594 / UL 2202, IEC 61851-1, UL 9741 (bidirectional)",
    "e-mobility": "UL 2849 (e-bike systems), UL 2271 (LEV batteries), UL 2272 (personal e-mobility)",
    "ev-traction": "FMVSS 305a, UL 2580, ISO 6469-1, UN ECE R100",
    "robotics": "ISO 10218, ISO 13482, UL 3300, ANSI/A3 R15.08, UL 4600 (autonomy)",
}
