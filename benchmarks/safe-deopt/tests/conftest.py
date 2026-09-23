# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Shared pytest configuration for benchmarks/safe-deopt/tests/.

Registers the ``robustness_only`` marker used by ``test_guarantee_contracts.py`` to flag
tests that assert a CURRENTLY-BROKEN or intentionally-incomplete guarantee's actual
behavior (so the suite stays green while loudly documenting the gap), as opposed to a
held guarantee. See ACCEPTANCE_PLAN_V2.md ss2: "Intentionally-broken guarantees go in a
separately labeled robustness experiment, excluded from valid-guarantee conclusions."

Deliberately scoped to this tests/ directory (not the repo-root pyproject.toml) so it
never touches shared HUF test configuration outside this benchmark.
"""

from __future__ import annotations


def pytest_configure(config) -> None:
	config.addinivalue_line(
		"markers",
		"robustness_only: asserts CURRENT (known-broken or intentionally-incomplete) "
		"behavior of a guarantee contract, not a held guarantee -- excluded from "
		"valid-guarantee conclusions per ACCEPTANCE_PLAN_V2.md ss2.",
	)
