"""Filter, rank and render recalls as a weekly digest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Optional

from .model import SAFETY, STANDARD_HINTS, Recall, classify


def filter_relevant(recalls: Iterable[Recall], topics: Optional[set] = None,
                    extra_topics: Optional[dict] = None) -> list:
    out = []
    for r in recalls:
        classify(r, extra_topics)
        if not r.topics:
            continue
        if not (re.search(SAFETY, r.text()) or r.flags):
            continue  # chemical-content or labelling withdrawals, no physical hazard
        if topics and not (set(r.topics) & topics):
            continue
        out.append(r)
    return sorted(out, key=lambda r: (r.score, r.date), reverse=True)


def merge_state(state_path: Optional[Path], recalls: list) -> list:
    """Merge with previously seen recalls so daily runs build up a week."""
    if not state_path:
        return recalls
    seen = {}
    if state_path.exists():
        for d in json.loads(state_path.read_text()):
            seen[(d["source"], d["id"])] = Recall(**d)
    for r in recalls:
        seen[(r.source, r.id)] = r
    merged = list(seen.values())
    state_path.write_text(json.dumps([r.to_dict() for r in merged], indent=1))
    return merged


def _short(text: str, n: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def render_markdown(recalls: list, since: str, until: str, top: int = 3, min_score: int = 3) -> str:
    lines = [f"# Recall radar: {since} to {until}", ""]
    if not recalls:
        return "\n".join(lines + ["No battery, charging, e-mobility, energy storage or robotics recalls in this window.", ""])
    by_src = {}
    for r in recalls:
        by_src[r.source] = by_src.get(r.source, 0) + 1
    lines.append(f"{len(recalls)} relevant recalls · " + " · ".join(f"{k} {v}" for k, v in sorted(by_src.items())))
    lines.append("")
    picks = [r for r in recalls if r.score >= min_score][:top]
    if picks:
        lines += ["## Worth a post", ""]
    for r in picks:
        units = f"{r.units:,} units · " if r.units else ""
        topics = list(r.topics)
        if "battery" in topics and set(topics) & {"ev-traction", "e-mobility", "energy-storage"}:
            topics.remove("battery")  # the specific topic's standards already cover the battery
        hints = "; ".join(STANDARD_HINTS[t] for t in topics if t in STANDARD_HINTS)
        lines.append(f"**{r.title}** ({r.source} {r.id}, {r.date})")
        lines.append(f"{units}{_short(r.hazard or r.description)}")
        if hints:
            lines.append(f"Standards to look at: {hints}")
        if r.url:
            lines.append(r.url)
        lines.append("")
    lines += ["## All relevant recalls", "", "| Score | Date | Source | Topics | Recall | Units |", "|---|---|---|---|---|---|"]
    for r in recalls:
        title = r.title.replace("|", "/")
        link = f"[{_short(title, 80)}]({r.url})" if r.url else _short(title, 80)
        lines.append(f"| {r.score} | {r.date} | {r.source} | {', '.join(r.topics)} | {link} | "
                     f"{f'{r.units:,}' if r.units else ''} |")
    lines.append("")
    return "\n".join(lines)
