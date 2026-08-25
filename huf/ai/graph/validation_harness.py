# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Validation harness for Procedures (T-50).

Implements GOAL.md §5 and I10 ("one successful trajectory is not proof"). Four pieces:

1. **Fixtures** (§5.2) -- :func:`find_benchmark_dir` / :func:`load_benchmark` load the four
   benchmarks already checked into ``$TRACK/benchmarks/`` (scenario, seed data, expected
   procedure, executable ``invariants.py``). This module never rewrites those invariants; it
   only loads and runs them.
2. **Shadow execution** (§5.1) -- :func:`should_shadow` / :func:`run_shadow` run the
   deterministic path alongside normal agentic execution, SAMPLED and budget-capped, and
   structurally forbidden from ever touching a write Procedure.
3. **N-run comparison** (§5.3, I10) -- :func:`aggregate_runs` turns a list of per-run
   agentic-vs-deterministic measurements into one :class:`NRunReport` covering result
   equivalence, invariant correctness, tool/API call reduction, token reduction, latency,
   failure rate, permission envelope, and payload reduction.
4. **Promotion gate** (§5.4, I8/I10) -- :func:`evaluate_promotion` decides, from an
   :class:`NRunReport` (plus the write-specific checklist for mutating Procedures), whether a
   Procedure may be activated. It fails closed: no report, too few runs, or a missing write
   checklist item all mean "do not promote" -- there is no code path that defaults to yes.

MEASUREMENT HONESTY. This module is frappe-free and side-effect-free by design (mirrors
``procedure_runtime.execute_procedure``'s split: the pure core here takes measurements as
plain dataclasses, never talks to ``frappe`` or an LLM itself). It does not itself run an
agentic trajectory or a real ERPNext bench -- callers (tests, and eventually a bench-side
Frappe job) supply :class:`RunMetrics` for both the agentic and deterministic side of each
run. In this track's own tests those metrics come from the T-23/T-30/T-40 benchmark layer,
which is SIMULATED (hand-written fake tool invokers standing in for a live bench -- see
``huf/ai/tests/test_procedure_runtime.py`` and ``test_procedure_runtime_benchmark4.py``).
Any number produced by running *this module's own test suite* is therefore illustrative of
the comparison mechanism, not a measurement of production token/latency behaviour. A report
built from :func:`aggregate_runs` carries this in ``NRunReport.simulated`` -- callers must set
it accurately and consumers (e.g. a promotion decision surfaced to a human) must not present a
``simulated=True`` report as a production measurement.
"""

from __future__ import annotations

import importlib.util
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 1. Fixtures (GOAL.md 5.2)
# ---------------------------------------------------------------------------


def find_benchmark_dir(name: str, start: Path | None = None) -> Path | None:
	"""Walk ancestor directories of ``start`` (default: this file) looking for
	``benchmarks/<name>``.

	The benchmark tree lives at ``$TRACK/benchmarks/`` -- a sibling of the ``huf`` app
	checkout, not inside it -- so its nesting depth relative to this file varies with how the
	app is checked out (a worktree under ``$TRACK/wt/<task>/huf`` vs. the app mirrored
	directly as a sibling of ``benchmarks/``). Searching upward is what every existing
	benchmark test in this package already does (see ``_find_benchmark_1_dir`` in
	``test_procedure_runtime.py``); this is that same helper, generalised to any benchmark.
	"""
	here = (start or Path(__file__)).resolve()
	for parent in here.parents:
		candidate = parent / "benchmarks" / name
		if (candidate / "invariants.py").exists():
			return candidate
	return None


def _load_module_from_path(module_name: str, path: Path):
	spec = importlib.util.spec_from_file_location(module_name, path)
	module = importlib.util.module_from_spec(spec)
	sys.modules[module_name] = module
	spec.loader.exec_module(module)
	return module


@dataclass
class BenchmarkFixture:
	"""One benchmark's reviewed input/output/invariant fixtures (§5.2), loaded off disk.

	``invariants`` is the actual executed module from ``invariants.py`` -- this class never
	re-encodes the checks, only exposes them alongside the human-readable scenario docs.
	"""

	name: str
	directory: Path
	readme: str
	seed_data: str
	expected_procedure: str
	invariants: Any  # the loaded invariants.py module


def load_benchmark(name: str, start: Path | None = None) -> BenchmarkFixture:
	"""Load one benchmark's fixtures by directory name, e.g.
	``"benchmark-1-customer-context"``.

	Raises ``FileNotFoundError`` if the benchmark cannot be located -- callers that want a
	skipped test rather than a hard failure (the pattern every existing benchmark test in this
	package uses) should catch this and skip.
	"""
	directory = find_benchmark_dir(name, start=start)
	if directory is None:
		raise FileNotFoundError(f"benchmarks/{name} not found relative to {start or Path(__file__)}")

	def _read(filename: str) -> str:
		p = directory / filename
		return p.read_text() if p.exists() else ""

	invariants = _load_module_from_path(f"{name.replace('-', '_')}_invariants", directory / "invariants.py")
	return BenchmarkFixture(
		name=name,
		directory=directory,
		readme=_read("README.md"),
		seed_data=_read("seed-data.md"),
		expected_procedure=_read("expected-procedure.md"),
		invariants=invariants,
	)


ALL_BENCHMARK_NAMES = (
	"benchmark-1-customer-context",
	"benchmark-2-collection-prioritization",
	"benchmark-3-crm-followup",
	"benchmark-4-reconciliation",
)


# ---------------------------------------------------------------------------
# 2. Shadow execution (GOAL.md 5.1)
# ---------------------------------------------------------------------------


@dataclass
class ShadowConfig:
	"""Sampling and budget for shadow execution. Defaults are DELIBERATELY conservative --
	shadow execution runs the deterministic path a second time on top of normal agentic
	execution, so an unsampled or unbudgeted default would make validation itself the
	performance problem this feature exists to remove.

	``sample_rate``: fraction of eligible (read-only) runs to shadow, in [0, 1]. Default 0.05
	(1 in 20) -- enough to accumulate N-run evidence over normal traffic without doubling cost
	broadly.

	``max_shadow_runs_per_window`` / ``window_seconds``: a hard cap on shadow runs within a
	rolling window, independent of how many runs *would* be sampled -- protects against a
	traffic spike turning a low sample rate into a high absolute shadow volume. Default 20 per
	hour.
	"""

	sample_rate: float = 0.05
	max_shadow_runs_per_window: int = 20
	window_seconds: float = 3600.0

	def __post_init__(self):
		if not 0.0 <= self.sample_rate <= 1.0:
			raise ValueError(f"sample_rate must be in [0, 1], got {self.sample_rate}")
		if self.max_shadow_runs_per_window < 0:
			raise ValueError("max_shadow_runs_per_window must be >= 0")
		if self.window_seconds <= 0:
			raise ValueError("window_seconds must be > 0")


class ShadowBudget:
	"""In-process rolling-window counter enforcing ``ShadowConfig``'s budget.

	Plain in-memory state, matching this module's frappe-free design -- a bench-side caller
	that needs the budget shared across workers is expected to back this with a shared cache
	(e.g. Redis) using the same window semantics; this class is the reference implementation
	and the one used in this track's own tests.
	"""

	def __init__(self, config: ShadowConfig, clock: Callable[[], float] = time.monotonic):
		self._config = config
		self._clock = clock
		self._timestamps: list[float] = []

	def _prune(self, now: float) -> None:
		cutoff = now - self._config.window_seconds
		self._timestamps = [t for t in self._timestamps if t > cutoff]

	def try_consume(self) -> bool:
		"""Attempt to spend one unit of shadow budget. Returns whether it was granted."""
		now = self._clock()
		self._prune(now)
		if len(self._timestamps) >= self._config.max_shadow_runs_per_window:
			return False
		self._timestamps.append(now)
		return True

	def remaining(self) -> int:
		now = self._clock()
		self._prune(now)
		return max(0, self._config.max_shadow_runs_per_window - len(self._timestamps))


def should_shadow(
	*,
	is_read_only: bool,
	contains_writes: bool,
	config: ShadowConfig,
	budget: ShadowBudget,
	rng: Callable[[], float],
) -> bool:
	"""Decide whether this run should be shadowed. The write gate is unconditional and
	evaluated first: nothing below it -- sample rate, budget, caller intent -- can turn a
	write Procedure into a shadow-executed one.

	Structural, not conventional: this checks BOTH ``contains_writes`` and ``is_read_only``
	(the same complementary pair ``huf.ai.graph.cache.set_cached_result`` gates on for the
	same reason, D7/I8) rather than trusting either flag alone to have been derived correctly
	by whatever produced it -- a caller that only sets one of the two still gets refused if
	they disagree.
	"""
	if contains_writes or not is_read_only:
		return False
	if config.sample_rate <= 0.0:
		return False
	if rng() >= config.sample_rate:
		return False
	return budget.try_consume()


@dataclass
class RunMetrics:
	"""One side (agentic or deterministic) of one run's measurements. Plain data -- this
	module never computes these itself; callers own instrumenting their own execution path
	and handing the numbers in. See the module docstring's MEASUREMENT HONESTY note: metrics
	produced against the T-23/T-30/T-40 simulated tool layer are illustrative, not
	production numbers.
	"""

	output: Any = None
	success: bool = True
	tool_call_count: int = 0
	token_count: int = 0
	latency_seconds: float = 0.0
	payload_bytes: int = 0
	permission_scopes: frozenset[str] = field(default_factory=frozenset)
	error: str | None = None


def _approx_equal(a: Any, b: Any, *, rel_tol: float = 1e-6, abs_tol: float = 1e-6) -> bool:
	if isinstance(a, bool) or isinstance(b, bool):
		return a == b
	if isinstance(a, (int, float)) and isinstance(b, (int, float)):
		return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))
	if isinstance(a, dict) and isinstance(b, dict):
		return a.keys() == b.keys() and all(
			_approx_equal(a[k], b[k], rel_tol=rel_tol, abs_tol=abs_tol) for k in a
		)
	if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
		return len(a) == len(b) and all(
			_approx_equal(x, y, rel_tol=rel_tol, abs_tol=abs_tol) for x, y in zip(a, b, strict=True)
		)
	return a == b


def compare_results(agentic_output: Any, deterministic_output: Any) -> tuple[bool, str | None]:
	"""Structural, tolerance-aware equality check for §5.3's "result equivalence" measure.
	Returns ``(equivalent, reason)`` -- ``reason`` is ``None`` iff equivalent.
	"""
	if _approx_equal(agentic_output, deterministic_output):
		return True, None
	return False, f"agentic output {agentic_output!r} != deterministic output {deterministic_output!r}"


@dataclass
class ShadowResult:
	"""Outcome of one attempted shadow comparison."""

	sampled: bool
	agentic: RunMetrics | None = None
	deterministic: RunMetrics | None = None
	result_equivalent: bool | None = None
	reason: str | None = None
	shadow_error: str | None = None
	"""Set if the deterministic side itself raised. Shadow execution NEVER propagates this to
	the caller (it must not change user-visible behaviour, §5.1) -- it is captured here for
	the comparison record only.
	"""


def run_shadow(
	*,
	is_read_only: bool,
	contains_writes: bool,
	config: ShadowConfig,
	budget: ShadowBudget,
	agentic: RunMetrics,
	deterministic_runner: Callable[[], RunMetrics],
	rng: Callable[[], float] = random.random,
) -> ShadowResult:
	"""Run the deterministic path in shadow, if sampled, and compare it to the already-
	completed agentic run's metrics. Never raises -- a broken shadow comparison must not be
	able to break the (already-returned) agentic result it is shadowing.

	``deterministic_runner`` is a zero-arg callable the caller closes over the pinned
	Procedure version, input, and a ``tool_invoker`` with -- kept generic here so this module
	never imports ``procedure_runtime`` and never becomes a second place that knows how to run
	a graph.
	"""
	if not should_shadow(
		is_read_only=is_read_only, contains_writes=contains_writes, config=config, budget=budget, rng=rng
	):
		return ShadowResult(sampled=False, agentic=agentic)

	try:
		deterministic = deterministic_runner()
	except Exception as exc:  # noqa: BLE001 -- shadow execution must never surface an error to the caller
		return ShadowResult(sampled=True, agentic=agentic, shadow_error=str(exc))

	equivalent, reason = compare_results(agentic.output, deterministic.output)
	return ShadowResult(
		sampled=True,
		agentic=agentic,
		deterministic=deterministic,
		result_equivalent=equivalent,
		reason=reason,
	)


# ---------------------------------------------------------------------------
# 3. N-run comparison (GOAL.md 5.3, I10)
# ---------------------------------------------------------------------------

MIN_REPRESENTATIVE_RUNS = 5
"""I10's "one successful trajectory is not proof" needs a plural floor. Five is the smallest
number that lets a single anomalous run be visibly an outlier rather than half the evidence;
:func:`evaluate_promotion` refuses to promote below this regardless of how good those few runs
looked (fail closed)."""


@dataclass
class RunRecord:
	"""One representative run's paired measurement, plus whether the Procedure's own
	``invariants.py`` checks passed against the deterministic output.
	"""

	agentic: RunMetrics
	deterministic: RunMetrics
	invariants_passed: bool


@dataclass
class NRunReport:
	"""§5.3's eight measures, aggregated across N :class:`RunRecord`. All ``*_pct`` reduction
	fields are ``(agentic - deterministic) / agentic``, so positive means the deterministic
	path is cheaper/faster/smaller; negative means it is worse. ``None`` when the agentic
	baseline is zero (nothing to compute a ratio against).
	"""

	n: int
	simulated: bool
	"""True if any input metric came from the T-23/T-30/T-40 simulated tool layer rather than
	a live bench -- see module docstring. Must be threaded through honestly by the caller."""

	result_equivalence_rate: float
	invariant_pass_rate: float
	failure_rate: float
	"""Fraction of runs where the deterministic side's ``success`` was False."""

	tool_call_reduction_pct: float | None
	token_reduction_pct: float | None
	latency_reduction_pct: float | None
	payload_reduction_pct: float | None

	permission_envelope_is_subset: bool
	"""True iff, on every run, the deterministic side's ``permission_scopes`` was a subset of
	the agentic side's -- the deterministic path must never need MORE authority than the
	agentic trajectory it is replacing."""

	records: list[RunRecord] = field(default_factory=list)


def _reduction_pct(agentic_total: float, deterministic_total: float) -> float | None:
	if agentic_total == 0:
		return None
	return (agentic_total - deterministic_total) / agentic_total


def aggregate_runs(records: list[RunRecord], *, simulated: bool) -> NRunReport:
	"""Turn N paired runs into one :class:`NRunReport`. ``simulated`` is not inferred --
	callers must state plainly whether these numbers came from a live bench or the simulated
	benchmark tool layer (see module docstring)."""
	n = len(records)
	if n == 0:
		return NRunReport(
			n=0,
			simulated=simulated,
			result_equivalence_rate=0.0,
			invariant_pass_rate=0.0,
			failure_rate=1.0,
			tool_call_reduction_pct=None,
			token_reduction_pct=None,
			latency_reduction_pct=None,
			payload_reduction_pct=None,
			permission_envelope_is_subset=False,
			records=[],
		)

	equivalences = []
	invariant_passes = 0
	failures = 0
	agentic_tools = agentic_tokens = agentic_latency = agentic_payload = 0.0
	det_tools = det_tokens = det_latency = det_payload = 0.0
	envelope_subset = True

	for rec in records:
		equivalent, _ = compare_results(rec.agentic.output, rec.deterministic.output)
		equivalences.append(equivalent)
		if rec.invariants_passed:
			invariant_passes += 1
		if not rec.deterministic.success:
			failures += 1

		agentic_tools += rec.agentic.tool_call_count
		det_tools += rec.deterministic.tool_call_count
		agentic_tokens += rec.agentic.token_count
		det_tokens += rec.deterministic.token_count
		agentic_latency += rec.agentic.latency_seconds
		det_latency += rec.deterministic.latency_seconds
		agentic_payload += rec.agentic.payload_bytes
		det_payload += rec.deterministic.payload_bytes

		if not rec.deterministic.permission_scopes <= rec.agentic.permission_scopes:
			envelope_subset = False

	return NRunReport(
		n=n,
		simulated=simulated,
		result_equivalence_rate=sum(equivalences) / n,
		invariant_pass_rate=invariant_passes / n,
		failure_rate=failures / n,
		tool_call_reduction_pct=_reduction_pct(agentic_tools, det_tools),
		token_reduction_pct=_reduction_pct(agentic_tokens, det_tokens),
		latency_reduction_pct=_reduction_pct(agentic_latency, det_latency),
		payload_reduction_pct=_reduction_pct(agentic_payload, det_payload),
		permission_envelope_is_subset=envelope_subset,
		records=list(records),
	)


# ---------------------------------------------------------------------------
# 4. Promotion gate (GOAL.md 5.4, I8/I10)
# ---------------------------------------------------------------------------


@dataclass
class PromotionThresholds:
	"""Minimum bars a Procedure must clear to be promoted. Defaults are strict on purpose --
	§5.4: "I would not automatically promote write Recipes in early versions."""

	min_runs: int = MIN_REPRESENTATIVE_RUNS
	min_result_equivalence_rate: float = 1.0
	min_invariant_pass_rate: float = 1.0
	max_failure_rate: float = 0.0
	require_permission_envelope_subset: bool = True
	min_tool_call_reduction_pct: float = 0.0
	"""A deterministic path that is not cheaper than the agentic one has no efficiency case
	for promotion (I10's whole point) even if it is otherwise correct; default 0.0 requires
	at least parity, never a regression."""


@dataclass
class WriteChecklist:
	"""§5.4's extra sequence for mutating Procedures: compile -> static security validation
	-> fixtures -> dry-run -> rollback/sandbox tests -> idempotency test -> human review ->
	activate. ``compile``/``static security validation``/``fixtures`` are already covered by
	the base :class:`NRunReport` checks (a report cannot exist without the graph having been
	built and executed against fixtures); this checklist is the four steps the N-run report
	does not itself express. All fields default to ``False`` (fail closed) -- there is no
	value that makes an unset checklist item read as "done".
	"""

	dry_run_passed: bool = False
	rollback_or_sandbox_tested: bool = False
	idempotency_test_passed: bool = False
	human_reviewed: bool = False


@dataclass
class PromotionDecision:
	approved: bool
	reasons: list[str] = field(default_factory=list)
	"""Reasons the decision came out this way -- always populated on rejection; may be
	populated on approval too (e.g. noting a report was simulated)."""


def evaluate_promotion(
	report: NRunReport | None,
	*,
	contains_writes: bool,
	thresholds: PromotionThresholds | None = None,
	write_checklist: WriteChecklist | None = None,
) -> PromotionDecision:
	"""Decide whether a Procedure may be activated. Fails closed at every branch: absent or
	insufficient evidence is always a rejection, never a default approval.

	``contains_writes`` drives the extra §5.4 checklist -- read the docstring on
	:class:`WriteChecklist` for why those four fields exist on top of the base report checks.
	I8 (no automatic activation of write Procedures) is enforced here structurally: a write
	Procedure with an empty/default ``WriteChecklist`` -- including simply omitting the
	argument -- is rejected, because every field of that checklist defaults to False.
	"""
	thresholds = thresholds or PromotionThresholds()
	reasons: list[str] = []

	if report is None:
		return PromotionDecision(
			approved=False,
			reasons=["no N-run report supplied -- absence of evidence is not evidence of readiness (I10)"],
		)

	if report.n < thresholds.min_runs:
		reasons.append(f"only {report.n} run(s) measured, need >= {thresholds.min_runs} (I10)")

	if report.result_equivalence_rate < thresholds.min_result_equivalence_rate:
		reasons.append(
			f"result equivalence rate {report.result_equivalence_rate:.2%} < "
			f"{thresholds.min_result_equivalence_rate:.2%}"
		)

	if report.invariant_pass_rate < thresholds.min_invariant_pass_rate:
		reasons.append(
			f"invariant pass rate {report.invariant_pass_rate:.2%} < {thresholds.min_invariant_pass_rate:.2%}"
		)

	if report.failure_rate > thresholds.max_failure_rate:
		reasons.append(f"failure rate {report.failure_rate:.2%} > {thresholds.max_failure_rate:.2%}")

	if thresholds.require_permission_envelope_subset and not report.permission_envelope_is_subset:
		reasons.append("deterministic path used permissions outside the agentic trajectory's envelope")

	if (
		report.tool_call_reduction_pct is None
		or report.tool_call_reduction_pct < thresholds.min_tool_call_reduction_pct
	):
		reasons.append(
			f"tool/API call reduction {report.tool_call_reduction_pct!r} < "
			f"{thresholds.min_tool_call_reduction_pct:.2%} (or unmeasurable)"
		)

	if contains_writes:
		checklist = write_checklist or WriteChecklist()
		if not checklist.dry_run_passed:
			reasons.append("write Procedure: dry-run not recorded as passed (I8/§5.4)")
		if not checklist.rollback_or_sandbox_tested:
			reasons.append("write Procedure: rollback/sandbox test not recorded as passed (I8/§5.4)")
		if not checklist.idempotency_test_passed:
			reasons.append("write Procedure: idempotency test not recorded as passed (I8/D5/§5.4)")
		if not checklist.human_reviewed:
			reasons.append("write Procedure: human review not recorded (I8 -- no automatic activation, ever)")

	if reasons:
		return PromotionDecision(approved=False, reasons=reasons)

	if report.simulated:
		reasons.append(
			"evidence is from the simulated T-23/T-30/T-40 tool layer, not a live bench -- "
			"approved on that basis only; re-validate against production before relying on these numbers"
		)
	return PromotionDecision(approved=True, reasons=reasons)
