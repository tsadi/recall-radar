"""Fetchers and normalizers for CPSC, NHTSA and EU Safety Gate.

Only the standard library is used so the tool runs anywhere, including a
scheduled GitHub Action.

* CPSC: documented Recalls Retrieval REST service (saferproducts.gov).
* NHTSA: the Recalls dataset on data.transportation.gov (Socrata, 6axg-epim).
* EU Safety Gate: the public JSON endpoints the Safety Gate website itself
  uses (latest-alerts list plus per-alert detail). These are not a
  documented API and can change; the latest-alerts list only returns the
  most recent alerts, so schedule the tool daily and let the state file
  accumulate the week.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import date
from typing import Callable, Optional

from .model import Recall

UA = {"User-Agent": "recall-radar/0.1 (+https://github.com/tsadi/recall-radar)", "Accept": "application/json"}

CPSC_URL = "https://www.saferproducts.gov/RestWebServices/Recall"
NHTSA_URL = "https://data.transportation.gov/resource/6axg-epim.json"
SG_BASE = "https://ec.europa.eu/safety-gate-alerts/public/api/notification"

Fetch = Callable[[str, Optional[bytes]], object]


def http_json(url: str, body: Optional[bytes] = None, timeout: int = 60):
    headers = dict(UA)
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _int(v) -> Optional[int]:
    """First whole number in a value like '18,400' or 'About 12,000 (in addition, 900 in Canada)'."""
    m = re.search(r"\d[\d,]*", str(v or ""))
    return int(m.group().replace(",", "")) if m else None


# ------------------------------------------------------------------ CPSC

def cpsc_url(since: date, until: date) -> str:
    q = {"format": "json", "RecallDateStart": since.isoformat(), "RecallDateEnd": until.isoformat()}
    return f"{CPSC_URL}?{urllib.parse.urlencode(q)}"


def normalize_cpsc(rec: dict) -> Recall:
    names = lambda key: "; ".join(x.get("Name", "") for x in rec.get(key) or [] if x.get("Name"))  # noqa: E731
    products = rec.get("Products") or []
    units = None
    for p in products:
        units = _int(p.get("NumberOfUnits")) or units
    return Recall(
        source="CPSC",
        id=str(rec.get("RecallNumber") or rec.get("RecallID")),
        date=str(rec.get("RecallDate", ""))[:10],
        title=rec.get("Title", "").strip(),
        hazard=names("Hazards"),
        description=rec.get("Description", "") or "",
        remedy=names("Remedies"),
        manufacturer=names("Manufacturers"),
        country="; ".join(x.get("Country", "") for x in rec.get("ManufacturerCountries") or []),
        units=units,
        url=rec.get("URL", ""),
    )


def fetch_cpsc(since: date, until: date, fetch: Fetch = http_json) -> list:
    data = fetch(cpsc_url(since, until), None) or []
    return [normalize_cpsc(r) for r in data]


# ----------------------------------------------------------------- NHTSA

def nhtsa_url(since: date, until: date, limit: int = 5000) -> str:
    where = (f"report_received_date >= '{since.isoformat()}T00:00:00' AND "
             f"report_received_date <= '{until.isoformat()}T23:59:59'")
    q = {"$where": where, "$limit": str(limit), "$order": "report_received_date DESC"}
    return f"{NHTSA_URL}?{urllib.parse.urlencode(q)}"


def normalize_nhtsa(rec: dict) -> Recall:
    flags = []
    if str(rec.get("do_not_drive", "")).lower() == "yes":
        flags.append("do_not_drive")
    if str(rec.get("fire_risk_when_parked", "")).lower() == "yes":
        flags.append("fire_when_parked")
    link = rec.get("recall_link") or {}
    return Recall(
        source="NHTSA",
        id=rec.get("nhtsa_id", ""),
        date=str(rec.get("report_received_date", ""))[:10],
        title=f"{rec.get('manufacturer', '').strip()}: {rec.get('subject', '').strip()}",
        hazard=rec.get("consequence_summary", "") or "",
        description=" ".join(x for x in [rec.get("component", ""), rec.get("defect_summary", "")] if x),
        remedy=rec.get("corrective_action", "") or "",
        manufacturer=rec.get("manufacturer", ""),
        units=_int(rec.get("potentially_affected")),
        url=link.get("url", "") if isinstance(link, dict) else str(link),
        flags=flags,
    )


def fetch_nhtsa(since: date, until: date, fetch: Fetch = http_json) -> list:
    data = fetch(nhtsa_url(since, until), None) or []
    return [normalize_nhtsa(r) for r in data]


# ----------------------------------------------------------- Safety Gate

def normalize_safetygate(detail: dict) -> Recall:
    product = detail.get("product") or {}
    versions = product.get("versions") or [{}]
    pv = versions[0] if versions else {}
    risk = detail.get("risk") or {}
    rv = (risk.get("versions") or [{}])[0]
    risk_types = ", ".join(x.get("name", "").title() for x in risk.get("riskType") or [])
    measures = (detail.get("measureTaken") or {}).get("measures") or []
    remedy = "; ".join((m.get("measureCategory") or {}).get("name", "").replace("_", " ").title() for m in measures)
    category = (product.get("productCategory") or {}).get("name", "").replace("_", " ").title()
    name = product.get("nameSpecific") or pv.get("name") or product.get("name") or ""
    return Recall(
        source="SafetyGate",
        id=detail.get("reference", str(detail.get("id", ""))),
        date=str(detail.get("publicationDate", ""))[:10],
        title=f"{category}: {name}".strip(": "),
        hazard=". ".join(x for x in [risk_types, rv.get("riskDescription", "")] if x),
        description=" ".join(x for x in [pv.get("description", ""), rv.get("legalProvision", "")] if x),
        remedy=remedy,
        country=(detail.get("country") or {}).get("name", ""),
        url=f"https://ec.europa.eu/safety-gate-alerts/screen/webReport/alertDetail/{detail.get('id', '')}",
    )


def fetch_safetygate(since: date, until: date, fetch: Fetch = http_json, max_alerts: int = 100) -> list:
    latest = fetch(f"{SG_BASE}/carousel/?", json.dumps({"language": "en"}).encode()) or {}
    out = []
    for item in (latest.get("content") or [])[:max_alerts]:
        d = str(item.get("publicationDate", ""))[:10]
        if d and not (since.isoformat() <= d <= until.isoformat()):
            continue
        detail = fetch(f"{SG_BASE}/{item['id']}?language=en", None)
        out.append(normalize_safetygate(detail))
    return out


FETCHERS = {"cpsc": fetch_cpsc, "nhtsa": fetch_nhtsa, "safetygate": fetch_safetygate}
