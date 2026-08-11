"""Deterministic scoring/ranking helpers for HUF app capability resource discovery.

Pure functions only: no frappe DB access, no writes. Callers pass in a
``frappe.get_meta(doctype)``-like meta object and any pre-computed signals
(exposure, submittability, link counts).
"""

from huf.ai.capability_discovery.models import VISIBILITY_LEVELS

# Substrings (case-insensitive) that mark a DocType name as an operational or
# supporting object rather than a primary business object. Used both to
# de-prioritize scoring and to inform (not gate) eligibility.
DEPRIORITIZED_NAME_PATTERNS = ("settings", "log", "setup", "detail")


def is_eligible_business_object(doctype_meta) -> bool:
    """Whether a DocType is a candidate business object at all.

    Simple boolean gate: excludes child tables and single DocTypes. Naming
    heuristics (Settings/Log/etc) are handled by score_resource /
    visibility_for_score, not here.
    """
    return not doctype_meta.istable and not doctype_meta.issingle


def score_resource(doctype_meta, *, is_exposed=False, submittable=False, link_count=0) -> float:
    """Deterministic score for ranking a DocType as a discoverable resource.

    Starts at 0.0 and adds/subtracts fixed weights:
      +100 if is_exposed (HUF App exposed_tables always wins, per plan §6.2)
      +10  if submittable
      + min(link_count, 10) for how many other DocTypes link to it
      -20  if the DocType name matches a de-prioritized naming pattern
    """
    score = 0.0
    if is_exposed:
        score += 100
    if submittable:
        score += 10
    score += min(link_count, 10)
    if _matches_deprioritized_pattern(doctype_meta.name):
        score -= 20
    return score


def visibility_for_score(score, is_exposed=False) -> str:
    """Map a resource score to one of models.VISIBILITY_LEVELS.

    "recommended" when exposed or score >= 15, "normal" when score >= 0,
    otherwise "advanced".
    """
    if is_exposed or score >= 15:
        visibility = "recommended"
    elif score >= 0:
        visibility = "normal"
    else:
        visibility = "advanced"
    assert visibility in VISIBILITY_LEVELS
    return visibility


def _matches_deprioritized_pattern(doctype_name: str) -> bool:
    lowered = doctype_name.lower()
    return any(pattern in lowered for pattern in DEPRIORITIZED_NAME_PATTERNS)
