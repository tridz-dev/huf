"""Test runs: a flow run that reads for real but never sends or changes anything outside the flow.

* :mod:`~huf.ai.flow.testrun.effects` classifies every tool as ``reads``, ``changes`` or ``sends``.
* :mod:`~huf.ai.flow.testrun.simulate` writes the believable "Would send ..." output a skipped step returns.
* :mod:`~huf.ai.flow.testrun.gate` decides, for a node or an agent's tool call, whether to run or simulate.
"""

MODE_TEST = "test"
MODE_REAL = "real"
RUN_MODES = (MODE_REAL, MODE_TEST)

# The values stored on ``Flow Run.run_mode`` (a Select).
STORED_TEST = "Test"
STORED_REAL = "Real"


def normalize_mode(mode) -> str:
	"""``"test"`` or ``"real"`` (case does not matter). Anything else is a mistake the caller must hear about."""
	value = str(mode or MODE_REAL).strip().lower()
	if value not in RUN_MODES:
		raise ValueError("Choose Test run or Run for real.")
	return value


def stored_mode(mode) -> str:
	return STORED_TEST if normalize_mode(mode) == MODE_TEST else STORED_REAL
