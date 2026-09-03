"""Problematic-developer signal layers — evidence aggregation, not verdicts.

Each layer (registry / forum / web) emits ``signal`` dicts about a company or a
person, keyed for later linkage by ЕИК or normalized name. The matcher
(:mod:`crawlers.signals.match`) decides *which* developer/person a free-text
source is about, and with what confidence.
"""

from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
