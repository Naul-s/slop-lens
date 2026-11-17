"""Importing this package registers every static rule into model.RULES."""
from . import visual, layout, copy, imagery, ux, code, game, a11y, render, perception, screentext  # noqa: F401
from ..model import RULES


def get_rules(kind=None, category=None, source=None):
    out = RULES
    if source:
        out = [r for r in out if r.source == source]
    if kind:
        out = [r for r in out if kind in r.applies]
    if category:
        out = [r for r in out if r.category == category]
    return out


def find_rule(rule_id):
    from ..rubric import RUBRIC
    rid = rule_id.upper().strip()
    for r in RULES:
        if r.id == rid:
            return r
    if rid in RUBRIC:
        return RUBRIC[rid][0]
    return None
