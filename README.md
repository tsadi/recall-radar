# recall-radar

A weekly digest of battery, charging, e-mobility, energy storage, EV traction battery and robotics recalls from three regulators:

- **CPSC** (US consumer products), through the Recalls Retrieval REST service
- **NHTSA** (US vehicles and equipment), through the Recalls dataset on data.transportation.gov
- **EU Safety Gate** (non-food products across the EU/EEA), through the JSON endpoints the Safety Gate site uses

It keeps the recalls that matter to people who certify batteries, chargers, power electronics and robots, scores them (fire, injury or death language, do-not-drive and park-outside flags, number of units), and writes a markdown digest with the top items, the standards a reader would check first, and a table of everything else.

I use it as the source for a weekly "failure file": what failed, which standard covers it, and what I would check first on a design review.

## Example

```
pip install -e .
recall-radar --days 7 -o digest.md
```

Sample output, generated from the test fixtures:

```
# Recall radar: 2026-09-28 to 2026-10-05

3 relevant recalls · CPSC 1 · NHTSA 1 · SafetyGate 1

## Worth a post

**Example EV Co.: High Voltage Battery May Short Circuit** (NHTSA 26V640000, 2026-10-02)
18,400 units · An internal short can lead to a battery fire, increasing the risk of injury.
Standards to look at: FMVSS 305a, UL 2580, ISO 6469-1, UN ECE R100
https://www.nhtsa.gov/recalls?nhtsaId=26V640000

| Score | Date | Source | Topics | Recall | Units |
...
```

Options:

```
recall-radar --days 14 --sources cpsc,nhtsa --topics battery,e-mobility --json out.json
recall-radar --state data/state.json         # accumulate across daily runs
recall-radar --from-json saved.json          # offline, from a previous run
```

## Scheduled digest

`.github/workflows/digest.yml` runs daily on GitHub Actions, keeps a state file in `data/`, and commits `digests/latest.md` with the last seven days. Daily matters for Safety Gate: its latest-alerts list only holds the most recent alerts, so a weekly run would miss most of the week.

## Topics and scoring

Topics are keyword patterns in `recall_radar/model.py` (`battery`, `energy-storage`, `charging`, `e-mobility`, `ev-traction`, `robotics`). Add your own with the `extra_topics` argument or by editing the file. Recalls with no matching topic are dropped.

| Signal | Points |
|---|---|
| fire, burn, overheat, explosion, thermal runaway language | 3 |
| death, fatal, serious injury, hospital language | 4 |
| NHTSA do-not-drive or park-outside flag | 4 |
| 1,000 / 10,000 / 100,000+ units | 1 / 2 / 3 |
| matching topics (up to 2) | 1 each |

## Caveats

- The Safety Gate endpoints are the ones its public website calls. They are not a documented API and can change without notice. If they do, CPSC and NHTSA keep working and the run logs a warning.
- Keyword matching is blunt. Expect the occasional false positive (a "solar" garden light) and miss (a recall that never says "battery"). Read the source before you post about it.
- Standards hints are a starting point for a reader, not a compliance determination.

## Tests

Tests run offline against fixtures in `tests/fixtures/`:

```
pip install pytest
pytest
```

## License

MIT. Built by [Tsadi Shvo](https://www.linkedin.com/in/tsadishvo/), product safety and compliance for robotics, EV/BESS and power electronics.
