"""Tests run offline against recorded / synthetic fixtures.

nhtsa.json starts from a real record from the data.transportation.gov feed;
the battery record and the CPSC and Safety Gate fixtures are synthetic but
follow each source's published field layout.
"""

import json
from datetime import date
from pathlib import Path

from recall_radar import filter_relevant, merge_state, render_markdown
from recall_radar import sources
from recall_radar.cli import main

FIX = Path(__file__).resolve().parent / "fixtures"
SINCE, UNTIL = date(2026, 9, 28), date(2026, 10, 5)


def load(name):
    return json.loads((FIX / name).read_text())


def fake_fetch_list(data):
    return lambda url, body=None: data


def fake_safetygate():
    sg = load("safetygate.json")

    def fetch(url, body=None):
        if "carousel" in url:
            return sg["carousel"]
        return sg["details"][url.rsplit("/", 1)[1].split("?")[0]]
    return fetch


def test_nhtsa_normalize_and_flags():
    recs = sources.fetch_nhtsa(SINCE, UNTIL, fake_fetch_list(load("nhtsa.json")))
    ev = [r for r in recs if r.id == "26V640000"][0]
    assert ev.units == 18400
    assert "fire_when_parked" in ev.flags
    assert ev.url.endswith("26V640000")


def test_nhtsa_url_has_date_window():
    url = sources.nhtsa_url(SINCE, UNTIL)
    assert "2026-09-28T00%3A00%3A00" in url and "6axg-epim" in url


def test_cpsc_normalize():
    recs = sources.fetch_cpsc(SINCE, UNTIL, fake_fetch_list(load("cpsc.json")))
    bike = recs[0]
    assert bike.units == 12000 and bike.source == "CPSC"
    assert "ignite" in bike.hazard


def test_safetygate_normalize():
    recs = sources.fetch_safetygate(SINCE, UNTIL, fake_safetygate())
    assert len(recs) == 2
    pb = [r for r in recs if "power bank" in r.title.lower()][0]
    assert pb.country == "Germany" and "Fire" in pb.hazard


def test_filter_keeps_only_relevant_and_ranks():
    recs = (sources.fetch_nhtsa(SINCE, UNTIL, fake_fetch_list(load("nhtsa.json")))
            + sources.fetch_cpsc(SINCE, UNTIL, fake_fetch_list(load("cpsc.json")))
            + sources.fetch_safetygate(SINCE, UNTIL, fake_safetygate()))
    rel = filter_relevant(recs)
    titles = [r.title for r in rel]
    assert not any("Fairing" in t for t in titles)      # hitch / fairing recalls dropped
    assert not any("Pajamas" in t for t in titles)
    assert not any("Desk Lamp" in t for t in titles)
    assert rel[0].id == "26V640000"                      # fire when parked + EV battery ranks first
    assert {"battery", "e-mobility"} <= set([t for r in rel for t in r.topics])


def test_topic_filter():
    recs = sources.fetch_cpsc(SINCE, UNTIL, fake_fetch_list(load("cpsc.json")))
    assert filter_relevant(recs, {"robotics"}) == []


def test_state_accumulates(tmp_path):
    state = tmp_path / "state.json"
    a = sources.fetch_cpsc(SINCE, UNTIL, fake_fetch_list(load("cpsc.json")))
    merge_state(state, a)
    b = sources.fetch_nhtsa(SINCE, UNTIL, fake_fetch_list(load("nhtsa.json")))
    merged = merge_state(state, b)
    assert len(merged) == 4


def test_markdown():
    rel = filter_relevant(sources.fetch_cpsc(SINCE, UNTIL, fake_fetch_list(load("cpsc.json"))))
    md = render_markdown(rel, "2026-09-28", "2026-10-05")
    assert "Worth a post" in md and "UL 2849" in md
    assert "No battery" in render_markdown([], "a", "b")


def test_cli_offline(tmp_path, capsys):
    recs = filter_relevant(sources.fetch_cpsc(SINCE, UNTIL, fake_fetch_list(load("cpsc.json"))))
    p = tmp_path / "in.json"
    p.write_text(json.dumps([r.to_dict() for r in recs]))
    out = tmp_path / "digest.md"
    assert main(["--from-json", str(p), "--until", "2026-10-05", "-o", str(out)]) == 0
    assert "E-Bike" in out.read_text()


def _r(**kw):
    from recall_radar.model import Recall
    base = dict(source="CPSC", id="x", date="2026-10-01", title="")
    base.update(kw)
    return Recall(**base)


def test_rechargeable_is_not_a_charger_recall():
    r = filter_relevant([_r(title="Rechargeable Hand Warmers Recalled",
                            hazard="The lithium-ion battery can overheat and ignite.", units=77000)])[0]
    assert "battery" in r.topics
    assert "charging" not in r.topics and "ev-charging" not in r.topics
    md = render_markdown([r], "a", "b")
    assert "UL 2594" not in md and "UL 2054" in md


def test_ev_charger_gets_ev_standards():
    r = filter_relevant([_r(title="Level 2 EV Chargers Recalled", hazard="Can overheat, posing a fire hazard.")])[0]
    assert "ev-charging" in r.topics
    assert "UL 2594" in render_markdown([r], "a", "b")


def test_chemical_only_withdrawal_dropped():
    r = _r(source="SafetyGate", title="Electrical Appliances: Wireless mouse",
           hazard="Environment. The solders contain lead and cadmium.",
           description="Rechargeable wireless mouse with charging cable. Does not comply with RoHS 2.")
    assert filter_relevant([r]) == []


def test_low_score_not_worth_a_post():
    r = filter_relevant([_r(title="Power adapter recalled", hazard="Risk of electric shock.")])[0]
    assert r.score < 3
    md = render_markdown([r], "a", "b")
    assert "Worth a post" not in md and "Power adapter" in md
