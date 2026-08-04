# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Token estimation helpers for result payloads.

Frappe does not depend on ``tiktoken`` and we do not add it for V1.  The
estimate is a conservative character heuristic used only for context-budget
metadata and hard-limit checks, not for billing.
"""

import math


def estimate_tokens(value) -> int:
    """Return a heuristic token count for ``value``.

    - Strings: ``ceil(len(text) / 4)``.
    - Bytes: decoded as UTF-8 (replacing errors), then ``ceil(len / 4)``.
    - Dicts/lists: JSON-serialized then ``ceil(len / 4)``.
    - ``None``: ``0``.
    """
    if value is None:
        return 0
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value
    else:
        import json

        text = json.dumps(value, default=str)
    return max(1, math.ceil(len(text) / 4)) if text else 0
