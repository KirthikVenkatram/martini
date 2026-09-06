"""Turns a gate Violation into the one sentence an AD would say (Module 5).

gate/checker.py already builds Violation.reason as plain English --
using the performer's character name, resolved there while it still
has the shooting day in scope to look one up -- because a Violation
carries no reference back to `day` for this module to resolve a name
from itself. explain() is the seam every caller (scripts/recover.py,
agent/root.py, and later the console) reaches for that sentence
through, instead of reading .reason directly.
"""

from __future__ import annotations

from gate.checker import Violation


def explain(violation: Violation) -> str:
    return violation.reason
