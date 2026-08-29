"""Tests for the sampling-parameter rejection fallback in the LiteLLM provider.

`top_p` auto-recovery is new here; before this change `top_p` was sent
unconditionally with no rejection handling at all. `temperature` recovery already
existed, and its detector was hardened.

Two things are covered:

1. `_param_rejected()` -- the detector that decides whether a provider's
   BadRequestError actually names `temperature`/`top_p` as the rejected
   parameter. The pre-existing `temperature` check was a bare substring test,
   which providers defeat by listing the parameters they DO accept after naming
   the one they rejected ("Supported parameters: temperature, top_p"). The
   enumeration is stripped -- narrowly, so a rejection stated AFTER the list is
   still seen -- URLs are removed so a doc anchor like "#top_p" cannot trip it,
   and the parameter must match as a whole word next to a rejection verb.

2. The retry branches themselves, checked structurally. `run()` and
   `run_stream()` keep duplicate copies of this handler, and that duplication is
   the standing risk: a branch that caches the negative result and pops the
   parameter but forgets to re-issue the request leaves `stream`/`response`
   unbound on the first round, and pointing at the previous round's exhausted
   generator afterwards. A behavioural test needs a live provider; an AST check
   does not, and it fails loudly the next time the two copies drift apart.
"""

import ast
import pathlib
import unittest

from huf.ai.providers.litellm import _param_rejected

_LITELLM_SRC = pathlib.Path(__file__).resolve().parents[1] / "providers" / "litellm.py"

# Which local name each function must rebind when it retries.
_RETRY_TARGET = {"run": "response", "run_stream": "stream"}
_RETRY_CALL = "_litellm_completion_with_retry"


def _find_function(tree, name):
	for node in ast.walk(tree):
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
			return node
	return None


def _conflict_branch_bodies(func):
	"""Map `is_<x>_conflict` flag name -> list of branch bodies testing it."""
	bodies = {}
	for node in ast.walk(func):
		if isinstance(node, ast.If) and isinstance(node.test, ast.Name):
			flag = node.test.id
			if flag.endswith("_conflict"):
				bodies.setdefault(flag, []).append(node.body)
	return bodies


def _rebinds_via_retry(body, target):
	"""True if `body` assigns `target` from a `_litellm_completion_with_retry` call."""
	for stmt in body:
		for node in ast.walk(stmt):
			if not isinstance(node, ast.Assign):
				continue
			names = {t.id for t in node.targets if isinstance(t, ast.Name)}
			if target not in names:
				continue
			for sub in ast.walk(node.value):
				if isinstance(sub, ast.Name) and sub.id == _RETRY_CALL:
					return True
	return False


class TestParamRejected(unittest.TestCase):
	def test_names_the_rejected_parameter(self):
		self.assertTrue(
			_param_rejected("unsupported parameter: 'top_p' is not supported with this model.", "top_p")
		)
		self.assertTrue(_param_rejected("`temperature` is deprecated for this model", "temperature"))
		self.assertTrue(_param_rejected("this model does not support top_p", "top_p"))

	def test_accepted_parameter_enumeration_is_not_a_rejection(self):
		# The real shape of the false positive: response_format is the rejected
		# parameter; temperature and top_p appear only in the accepted list.
		err = (
			"unsupported parameter: 'response_format' is not supported with this model. "
			"supported parameters: temperature, top_p, max_tokens."
		)
		self.assertFalse(_param_rejected(err, "top_p"))
		self.assertFalse(_param_rejected(err, "temperature"))

	def test_rejection_before_enumeration_still_detected(self):
		err = "`temperature` is deprecated for this model. supported parameters: top_p, max_tokens."
		self.assertTrue(_param_rejected(err, "temperature"))
		self.assertFalse(_param_rejected(err, "top_p"))

	def test_unrelated_errors_and_empty_input(self):
		self.assertFalse(_param_rejected("rate limit exceeded, please retry", "top_p"))
		self.assertFalse(_param_rejected("", "top_p"))
		self.assertFalse(_param_rejected(None, "top_p"))

	def test_matches_whole_word_only(self):
		self.assertFalse(_param_rejected("unsupported parameter: 'top_p_min' is not supported", "top_p"))


class TestRetryBranchesReissueTheRequest(unittest.TestCase):
	"""Both copies of the handler must actually re-send the request after retrying."""

	@classmethod
	def setUpClass(cls):
		cls.tree = ast.parse(_LITELLM_SRC.read_text(encoding="utf-8"))

	def _assert_branches_reissue(self, func_name):
		func = _find_function(self.tree, func_name)
		self.assertIsNotNone(func, f"{func_name}() not found in litellm.py")
		target = _RETRY_TARGET[func_name]
		bodies = _conflict_branch_bodies(func)

		for flag in ("is_temperature_conflict", "is_top_p_conflict"):
			self.assertIn(flag, bodies, f"{func_name}() has no {flag} branch")
			for body in bodies[flag]:
				self.assertTrue(
					_rebinds_via_retry(body, target),
					f"{func_name}(): the {flag} branch drops the parameter but never "
					f"reassigns `{target}` from {_RETRY_CALL}(), so the retried request "
					f"is never issued.",
				)

	def test_run_reissues(self):
		self._assert_branches_reissue("run")

	def test_run_stream_reissues(self):
		self._assert_branches_reissue("run_stream")

	def test_both_paths_handle_the_same_conflicts(self):
		run = _find_function(self.tree, "run")
		run_stream = _find_function(self.tree, "run_stream")
		sampling = {"is_temperature_conflict", "is_top_p_conflict"}
		self.assertEqual(
			sampling & set(_conflict_branch_bodies(run)),
			sampling & set(_conflict_branch_bodies(run_stream)),
			"run() and run_stream() handle different sampling-parameter conflicts; "
			"the two copies of this handler have drifted apart.",
		)


class TestNegativeCacheExpires(unittest.TestCase):
	def test_ttl_is_finite_and_applied_to_every_write(self):
		from huf.ai.providers.litellm import _SAMPLING_NEGATIVE_CACHE_TTL

		self.assertIsInstance(_SAMPLING_NEGATIVE_CACHE_TTL, int)
		self.assertGreater(_SAMPLING_NEGATIVE_CACHE_TTL, 0)

		# A negative result cached without a TTL never expires, so one false
		# positive would disable the parameter for that model permanently.
		src = _LITELLM_SRC.read_text(encoding="utf-8")
		for key in ("temperature_cache_key", "top_p_cache_key"):
			self.assertNotIn(
				f"frappe.cache().set_value({key}, 1)\n",
				src,
				f"{key} is cached without an expiry",
			)
