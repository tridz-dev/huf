# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) conformance suite for the MLX integration
across all three host states.

Context (T2.11): MLX is not Apple-Silicon-only, but Metal is. A host running
this suite (or CI) may have MLX not installed, installed without Metal
(Linux/CI), or installed with Metal (a real Mac). The invariant this suite
pins is that Huf must behave correctly in ALL THREE states, at every layer
that touches `probe_device()`:

    mlx_probe.probe_device / describe_probe_result
        -> MlxServerAdapter.get_device_info / describe_device / capability_overrides
        -> registry.get_adapter("mlx")
        -> local_runtime.test_provider_connection's mlx branch
        -> providers/litellm._normalize_model_name's mlx brand routing

Every host state is FAKED by patching `mlx_probe.probe_device` directly --
this suite never depends on whatever MLX state the real host happens to be
in, which would make two of the three states unreachable in CI.

This suite asserts behavior; it does not fix implementation bugs. A failing
assertion here is a genuine finding about the implementation, not a bug in
this file.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/local_runtimes/tests/test_mlx_conformance.py -v
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock.utils = MagicMock()
	frappe_mock._ = lambda x: x
	# `@frappe.whitelist()` must stay a transparent identity decorator, not
	# the default auto-mocked callable -- otherwise the imported
	# `test_provider_connection` is a bare MagicMock instead of the real
	# function, and every assertion below would silently test nothing.
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe"] = frappe_mock
	sys.modules["frappe.utils"] = frappe_mock.utils

try:
	import requests  # noqa: F401
except ImportError:
	sys.modules["requests"] = MagicMock()

# Stub litellm and its submodules before importing huf.ai.providers.litellm,
# mirroring huf/ai/tests/test_litellm_providers.py's header.
try:
	import litellm  # noqa: F401
except ImportError:
	litellm_mock = MagicMock()
	litellm_mock.InternalServerError = Exception
	litellm_mock.RateLimitError = Exception
	litellm_mock.APIError = Exception
	litellm_mock.BadRequestError = Exception
	litellm_mock.ContextWindowExceededError = Exception
	litellm_mock.utils.trim_messages = lambda x: x
	sys.modules["litellm"] = litellm_mock
	sys.modules["litellm.utils"] = litellm_mock.utils

from huf.ai import local_runtime  # noqa: E402
from huf.ai.local_runtimes import mlx_probe  # noqa: E402
from huf.ai.local_runtimes.mlx_server import MlxServerAdapter  # noqa: E402
from huf.ai.local_runtimes.registry import get_adapter  # noqa: E402
from huf.ai.local_runtimes.ollama import OllamaAdapter  # noqa: E402
from huf.ai.providers.litellm import _normalize_model_name  # noqa: E402


# The three host states under test, exactly as `probe_device()` would report
# them. "raising" is not a fourth state -- it exercises criterion 1 (never
# raises) against an internal MLX failure that isn't a plain ImportError.
NOT_INSTALLED = {
	"import_ok": False,
	"device": None,
	"metal_available": False,
	"mlx_version": None,
}
NO_METAL = {
	"import_ok": True,
	"device": "Device(cpu, 0)",
	"metal_available": False,
	"mlx_version": "0.32.0",
}
WITH_METAL = {
	"import_ok": True,
	"device": "Device(gpu, 0)",
	"metal_available": True,
	"mlx_version": "0.32.0",
}

ALL_STATES = {
	"not_installed": NOT_INSTALLED,
	"no_metal": NO_METAL,
	"with_metal": WITH_METAL,
}


def _make_provider_doc(**overrides):
	fields = {
		"is_local_llm": 1,
		"api_base_url": "http://localhost:8000",
		"provider_brand": "mlx",
	}
	fields.update(overrides)
	doc = SimpleNamespace(**fields)
	doc.get = lambda key, default=None: getattr(doc, key, default)
	doc.get_password = MagicMock(return_value="stored-secret-key")
	return doc


class TestProbeDeviceNeverRaises(unittest.TestCase):
	"""Criterion 1: probe_device() never raises, including on an arbitrary
	internal MLX exception (not just ImportError)."""

	def test_import_error_is_swallowed(self):
		with patch.dict(sys.modules, {"mlx": None}):
			# Simulate `import mlx` raising ImportError by making the module
			# genuinely absent from sys.modules and unimportable; probe_device
			# already defends this in production, so this just guards the
			# regression.
			try:
				result = mlx_probe.probe_device()
			except Exception as e:  # pragma: no cover - the assertion below fires first
				self.fail(f"probe_device() raised {e!r} on ImportError path")
			self.assertIsInstance(result, dict)

	def test_arbitrary_internal_exception_is_swallowed(self):
		"""A non-ImportError raised deep inside mlx internals must not
		propagate out of probe_device()."""
		fake_mlx = MagicMock()
		fake_mlx_core = MagicMock()
		fake_mlx_core.default_device.side_effect = RuntimeError("metal driver exploded")
		with patch.dict(sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mlx_core}):
			try:
				result = mlx_probe.probe_device()
			except Exception as e:
				self.fail(f"probe_device() raised {e!r} on internal exception path")
			self.assertIsInstance(result, dict)
			self.assertIn("import_ok", result)


class TestDescribeProbeResult(unittest.TestCase):
	"""Criterion 2: describe_probe_result returns the right constant per
	state."""

	def test_not_installed(self):
		self.assertEqual(
			mlx_probe.describe_probe_result(NOT_INSTALLED), mlx_probe.REASON_NOT_INSTALLED
		)

	def test_installed_no_metal(self):
		self.assertEqual(
			mlx_probe.describe_probe_result(NO_METAL), mlx_probe.REASON_DEGRADED_NO_METAL
		)

	def test_installed_with_metal(self):
		self.assertEqual(mlx_probe.describe_probe_result(WITH_METAL), mlx_probe.REASON_OK)


class TestCapabilityOverridesStateIndependent(unittest.TestCase):
	"""Criterion 3: capability_overrides on MlxServerAdapter returns
	supports_tools: None in all three host states, including a successful
	probe. MLX's server exposes no capability metadata, so the answer must
	not vary with host state."""

	def setUp(self):
		self.adapter = MlxServerAdapter()

	def test_supports_tools_none_regardless_of_state_or_probe_outcome(self):
		probes = [
			{"ok": True, "capabilities": [], "error": None},
			{"ok": False, "capabilities": [], "error": "model 'x' not found"},
		]
		for state_name, state in ALL_STATES.items():
			with patch.object(mlx_probe, "probe_device", return_value=state):
				for probe in probes:
					with self.subTest(state=state_name, probe_ok=probe["ok"]):
						overrides = self.adapter.capability_overrides(probe)
						self.assertIsNone(overrides["supports_tools"])


class TestGetAdapterStateIndependent(unittest.TestCase):
	"""Criterion 4: get_adapter("mlx") returns MlxServerAdapter in all three
	host states -- adapter selection must not depend on whether MLX is
	importable. This is the invariant that keeps a Linux bench able to drive
	a remote Mac MLX server."""

	def test_returns_mlx_server_adapter_in_all_states(self):
		for state_name, state in ALL_STATES.items():
			with patch.object(mlx_probe, "probe_device", return_value=state):
				with self.subTest(state=state_name):
					adapter = get_adapter("mlx")
					self.assertIsInstance(adapter, MlxServerAdapter)

	def test_case_insensitive_and_state_independent(self):
		for state_name, state in ALL_STATES.items():
			with patch.object(mlx_probe, "probe_device", return_value=state):
				with self.subTest(state=state_name):
					self.assertIsInstance(get_adapter("MLX"), MlxServerAdapter)


class TestGetDeviceInfoAndDescribeDeviceByState(unittest.TestCase):
	"""Sanity: MlxServerAdapter.get_device_info/describe_device correctly
	surface each faked state (ties layers 1-2 together)."""

	def setUp(self):
		self.adapter = MlxServerAdapter()

	def test_each_state_surfaces_correctly(self):
		expected_reason = {
			"not_installed": mlx_probe.REASON_NOT_INSTALLED,
			"no_metal": mlx_probe.REASON_DEGRADED_NO_METAL,
			"with_metal": mlx_probe.REASON_OK,
		}
		for state_name, state in ALL_STATES.items():
			with patch.object(mlx_probe, "probe_device", return_value=state):
				with self.subTest(state=state_name):
					info = self.adapter.get_device_info()
					self.assertEqual(info, state)
					self.assertEqual(self.adapter.describe_device(), expected_reason[state_name])


class TestProviderConnectionMessaging(unittest.TestCase):
	"""Criterion 5: test_provider_connection messaging across all three host
	states, with the server probe faked separately from local MLX state."""

	def setUp(self):
		patcher_get_doc = patch.object(
			local_runtime.frappe, "get_doc", return_value=_make_provider_doc()
		)
		self.mock_get_doc = patcher_get_doc.start()
		self.addCleanup(patcher_get_doc.stop)

		patcher_perm = patch.object(local_runtime.frappe, "has_permission", return_value=True)
		self.mock_perm = patcher_perm.start()
		self.addCleanup(patcher_perm.stop)

		patcher_get_all = patch.object(local_runtime.frappe, "get_all", return_value=[])
		self.mock_get_all = patcher_get_all.start()
		self.addCleanup(patcher_get_all.stop)

	def _run(self, server_probe_result, device_state):
		with patch.object(
			MlxServerAdapter, "probe_server", return_value=server_probe_result
		), patch.object(mlx_probe, "probe_device", return_value=device_state):
			return local_runtime.test_provider_connection("My MLX Provider")

	# -- reachable server: single most important assertion in this file --

	def test_reachable_server_ok_in_all_three_states(self):
		reachable = {"ok": True, "models": ["some-model"], "error": None}
		for state_name, state in ALL_STATES.items():
			with self.subTest(state=state_name):
				result = self._run(reachable, state)
				self.assertTrue(
					result["provider"]["ok"],
					f"expected ok=True for reachable server in state={state_name}, "
					f"got {result['provider']!r}",
				)
				self.assertIsNone(result["provider"]["error"])

	# -- unreachable server: local MLX state used as context per state --

	def test_unreachable_server_not_installed_mentions_reason(self):
		unreachable = {"ok": False, "models": [], "error": "Connection refused"}
		result = self._run(unreachable, NOT_INSTALLED)
		self.assertFalse(result["provider"]["ok"])
		self.assertIn(mlx_probe.REASON_NOT_INSTALLED, result["provider"]["error"])
		self.assertIn("Connection refused", result["provider"]["error"])

	def test_unreachable_server_degraded_no_metal_mentions_reason(self):
		unreachable = {"ok": False, "models": [], "error": "Connection refused"}
		result = self._run(unreachable, NO_METAL)
		self.assertFalse(result["provider"]["ok"])
		self.assertIn(mlx_probe.REASON_DEGRADED_NO_METAL, result["provider"]["error"])
		self.assertIn("Connection refused", result["provider"]["error"])

	def test_unreachable_server_with_metal_is_network_error_only(self):
		"""Regression guard: when local MLX is healthy, the network error must
		stand alone and must NOT contain REASON_OK's text ("MLX installed and
		Metal device available"). Reporting that as a failure reason was a
		real bug that was fixed."""
		unreachable = {"ok": False, "models": [], "error": "Connection refused"}
		result = self._run(unreachable, WITH_METAL)
		self.assertFalse(result["provider"]["ok"])
		self.assertEqual(result["provider"]["error"], "Connection refused")
		self.assertNotIn(mlx_probe.REASON_OK, result["provider"]["error"])

	def test_no_error_string_is_a_raw_traceback(self):
		unreachable = {"ok": False, "models": [], "error": "Connection refused"}
		reachable = {"ok": True, "models": [], "error": None}
		for server_result, state_name, state in [
			(unreachable, "not_installed", NOT_INSTALLED),
			(unreachable, "no_metal", NO_METAL),
			(unreachable, "with_metal", WITH_METAL),
			(reachable, "not_installed", NOT_INSTALLED),
			(reachable, "no_metal", NO_METAL),
			(reachable, "with_metal", WITH_METAL),
		]:
			with self.subTest(state=state_name, server_ok=server_result["ok"]):
				result = self._run(server_result, state)
				error = result["provider"]["error"]
				if error is not None:
					self.assertNotIn("Traceback (most recent call last)", error)


class TestLitellmDispatchStateIndependent(unittest.TestCase):
	"""Criterion 6: litellm dispatch is host-state independent -- the "mlx"
	brand yields an openai/ prefix regardless of state. Model routing is
	config, not a function of local hardware."""

	def test_mlx_brand_yields_openai_prefix_in_all_states(self):
		for state_name, state in ALL_STATES.items():
			with patch.object(mlx_probe, "probe_device", return_value=state):
				with self.subTest(state=state_name):
					result = _normalize_model_name("some-model", "mlx", brand="mlx")
					self.assertEqual(result, "openai/some-model")

	def test_mlx_brand_yields_openai_prefix_without_any_probe_call(self):
		"""_normalize_model_name must not itself consult MLX host state at
		all -- it's a pure string routing function."""
		with patch.object(
			mlx_probe, "probe_device", side_effect=AssertionError("must not be called")
		):
			result = _normalize_model_name("some-model", "mlx", brand="mlx")
			self.assertEqual(result, "openai/some-model")


class TestNothingRaisesAcrossLayers(unittest.TestCase):
	"""Criterion 7: nothing raises in any state, at any layer, including
	when the adapter for a non-mlx brand is exercised alongside an mlx probe
	patch (adapter selection independence check)."""

	def test_full_stack_all_states(self):
		for state_name, state in ALL_STATES.items():
			with patch.object(mlx_probe, "probe_device", return_value=state):
				with self.subTest(state=state_name):
					probe_result = mlx_probe.probe_device()
					self.assertIsInstance(probe_result, dict)
					reason = mlx_probe.describe_probe_result(probe_result)
					self.assertIsInstance(reason, str)
					adapter = get_adapter("mlx")
					self.assertIsInstance(adapter, MlxServerAdapter)
					info = adapter.get_device_info()
					self.assertIsInstance(info, dict)
					desc = adapter.describe_device()
					self.assertIsInstance(desc, str)
					overrides = adapter.capability_overrides(
						{"ok": True, "capabilities": [], "error": None}
					)
					self.assertIsNone(overrides["supports_tools"])
					# Non-mlx adapter selection must be unaffected by the mlx probe patch.
					self.assertIsInstance(get_adapter("ollama"), OllamaAdapter)
					name = _normalize_model_name("m", "mlx", brand="mlx")
					self.assertEqual(name, "openai/m")


if __name__ == "__main__":
	unittest.main()
