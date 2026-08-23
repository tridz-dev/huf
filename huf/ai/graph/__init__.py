"""Shared graph IR runtime pieces (Procedure + Flow profiles).

Frappe-free by design: submodules here (``transforms.py``, ``expressions.py``, ``permissions.py``)
must stay importable without a Frappe bench or site. Do not import ``frappe`` from this package's
``__init__``.
"""
