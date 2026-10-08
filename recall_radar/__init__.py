"""Weekly battery, charging, e-mobility, energy storage and robotics recall digest."""

from .digest import filter_relevant, merge_state, render_markdown  # noqa: F401
from .model import Recall, classify  # noqa: F401

__version__ = "0.1.0"
