"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from .digest import filter_relevant, merge_state, render_markdown
from .model import TOPICS, Recall
from .sources import FETCHERS


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="recall-radar",
                                 description="Battery, charging, e-mobility, energy storage and robotics recalls "
                                             "from CPSC, NHTSA and EU Safety Gate")
    ap.add_argument("--days", type=int, default=7, help="look-back window in days (default 7)")
    ap.add_argument("--until", type=date.fromisoformat, default=None, help="end date YYYY-MM-DD (default today)")
    ap.add_argument("--sources", default="cpsc,nhtsa,safetygate")
    ap.add_argument("--topics", default="", help=f"comma list to keep, from: {','.join(TOPICS)}")
    ap.add_argument("--state", type=Path, help="JSON file that accumulates recalls across runs")
    ap.add_argument("--from-json", type=Path, help="skip fetching; read normalized recalls from this file")
    ap.add_argument("-o", "--out", type=Path, help="write markdown digest")
    ap.add_argument("--json", type=Path, help="write relevant recalls as JSON")
    ap.add_argument("--top", type=int, default=3, help="items in the 'worth a post' section")
    args = ap.parse_args(argv)

    until = args.until or date.today()
    since = until - timedelta(days=args.days)

    recalls: list = []
    if args.from_json:
        recalls = [Recall(**d) for d in json.loads(args.from_json.read_text())]
    else:
        for name in [s.strip().lower() for s in args.sources.split(",") if s.strip()]:
            if name not in FETCHERS:
                print(f"error: unknown source {name!r}", file=sys.stderr)
                return 2
            try:
                got = FETCHERS[name](since, until)
                print(f"{name}: {len(got)} recalls", file=sys.stderr)
                recalls += got
            except Exception as e:  # one source failing should not kill the digest
                print(f"warning: {name} failed: {e}", file=sys.stderr)

    recalls = merge_state(args.state, recalls)
    recalls = [r for r in recalls if since.isoformat() <= r.date <= until.isoformat()]
    keep = {t.strip() for t in args.topics.split(",") if t.strip()} or None
    relevant = filter_relevant(recalls, keep)

    report = render_markdown(relevant, since.isoformat(), until.isoformat(), args.top)
    if args.out:
        args.out.write_text(report)
    if args.json:
        args.json.write_text(json.dumps([r.to_dict() for r in relevant], indent=1))
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
