"""Shared graph IR runtime pieces (Procedure + Flow profiles).

Frappe-free by design: submodules here (``transforms.py``, and siblings added by other T-1x tasks
such as ``expressions.py``) must stay importable without a Frappe bench/site. Do not import ``frappe``
from this package's ``__init__``.
"""
