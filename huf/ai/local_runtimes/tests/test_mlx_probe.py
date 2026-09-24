# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for the MLX runtime probe.

Fakes all three MLX host states (not installed, installed-but-no-Metal,
installed-with-Metal) via `sys.modules` / `unittest.mock`, so these tests
exercise every branch without requiring real Apple Metal hardware in CI.

`mlx_probe` itself never imports frappe, but `huf/__init__.py:4` does, so the
defensive stub below runs before the import -- the same pattern as
`huf/ai/tests/test_local_runtime_provider_connection_permission.py`. This
keeps the file runnable whether or not `tests/__init__.py` exists and whether
or not a bench is present; a `conftest.py`-only stub does not, because the
package `__init__` chain is imported before conftest applies.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/local_runtimes/tests/test_mlx_probe.py -v
"""

import sys
import types
import unittest
from unittest import mock
from unittest.mock import MagicMock

try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe"] = frappe_mock

from huf.ai.local_runtimes.mlx_probe import (
	REASON_DEGRADED_NO_METAL,
	REASON_NOT_INSTALLED,
	REASON_OK,
	describe_probe_result,
	probe_device,
)


def _make_fake_mlx_modules(version, device_str, metal_available, metal_raises=False):
	"""Build fake `mlx` / `mlx.core` modules for injection into sys.modules."""
	fake_mlx = types.ModuleType("mlx")
	fake_mlx.__version__ = version

	fake_mx = types.ModuleType("mlx.core")

	def _default_device():
		return device_str

	fake_mx.default_device = _default_device

	if metal_available is not None:
		fake_metal = types.ModuleType("mlx.core.metal")

		if metal_raises:
			def _is_available():
				raise RuntimeError("simulated internal MLX error")
		else:
			def _is_available():
				return metal_available

		fake_metal.is_available = _is_available
		fake_mx.metal = fake_metal

	fake_mlx.core = fake_mx
	return fake_mlx, fake_mx


class TestProbeDeviceNotInstalled(unittest.TestCase):
	"""State 1: `import mlx` fails -- package not installed."""

	def test_import_error_yields_unavailable_result(self):
		with mock.patch.dict(sys.modules, {"mlx": None, "mlx.core": None}):
			result = probe_device()

		self.assertEqual(
			result,
			{
				"import_ok": False,
				"device": None,
				"metal_available": False,
				"mlx_version": None,
			},
		)

	def test_reason_string_for_not_installed(self):
		result = {
			"import_ok": False,
			"device": None,
			"metal_available": False,
			"mlx_version": None,
		}
		self.assertEqual(describe_probe_result(result), REASON_NOT_INSTALLED)


class TestProbeDeviceDegraded(unittest.TestCase):
	"""State 2: MLX imports fine, but no Metal device (e.g. Linux/Intel Mac)."""

	def test_imports_but_no_metal(self):
		fake_mlx, fake_mx = _make_fake_mlx_modules(
			version="0.32.0", device_str="Device(cpu, 0)", metal_available=False
		)
		with mock.patch.dict(
			sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx}
		):
			result = probe_device()

		self.assertEqual(
			result,
			{
				"import_ok": True,
				"device": "Device(cpu, 0)",
				"metal_available": False,
				"mlx_version": "0.32.0",
			},
		)

	def test_reason_string_for_degraded(self):
		result = {
			"import_ok": True,
			"device": "Device(cpu, 0)",
			"metal_available": False,
			"mlx_version": "0.32.0",
		}
		self.assertEqual(describe_probe_result(result), REASON_DEGRADED_NO_METAL)


class TestProbeDeviceWorking(unittest.TestCase):
	"""State 3: MLX imports fine and Metal device is available."""

	def test_imports_with_metal(self):
		fake_mlx, fake_mx = _make_fake_mlx_modules(
			version="0.32.0", device_str="Device(gpu, 0)", metal_available=True
		)
		with mock.patch.dict(
			sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx}
		):
			result = probe_device()

		self.assertEqual(
			result,
			{
				"import_ok": True,
				"device": "Device(gpu, 0)",
				"metal_available": True,
				"mlx_version": "0.32.0",
			},
		)

	def test_reason_string_for_ok(self):
		result = {
			"import_ok": True,
			"device": "Device(gpu, 0)",
			"metal_available": True,
			"mlx_version": "0.32.0",
		}
		self.assertEqual(describe_probe_result(result), REASON_OK)


class TestProbeDeviceNeverRaises(unittest.TestCase):
	"""probe_device() must never raise, even on unexpected internal errors."""

	def test_metal_is_available_raises_internally(self):
		fake_mlx, fake_mx = _make_fake_mlx_modules(
			version="0.32.0",
			device_str="Device(gpu, 0)",
			metal_available=True,
			metal_raises=True,
		)
		with mock.patch.dict(
			sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx}
		):
			try:
				result = probe_device()
			except Exception as exc:  # pragma: no cover - failure path
				self.fail(f"probe_device() raised unexpectedly: {exc!r}")

		self.assertTrue(result["import_ok"])
		self.assertFalse(result["metal_available"])
		self.assertEqual(result["device"], "Device(gpu, 0)")
		self.assertEqual(result["mlx_version"], "0.32.0")

	def test_default_device_raises_internally(self):
		fake_mlx, fake_mx = _make_fake_mlx_modules(
			version="0.32.0", device_str="unused", metal_available=True
		)

		def _raising_default_device():
			raise RuntimeError("simulated internal MLX error")

		fake_mx.default_device = _raising_default_device

		with mock.patch.dict(
			sys.modules, {"mlx": fake_mlx, "mlx.core": fake_mx}
		):
			try:
				result = probe_device()
			except Exception as exc:  # pragma: no cover - failure path
				self.fail(f"probe_device() raised unexpectedly: {exc!r}")

		self.assertTrue(result["import_ok"])
		self.assertIsNone(result["device"])

	def test_import_raises_non_import_error(self):
		# Simulate an unexpected internal error surfacing during import itself
		# (not just ImportError), e.g. a broken native extension.
		with mock.patch(
			"builtins.__import__",
			side_effect=RuntimeError("simulated broken native extension"),
		):
			try:
				result = probe_device()
			except Exception as exc:  # pragma: no cover - failure path
				self.fail(f"probe_device() raised unexpectedly: {exc!r}")

		self.assertEqual(
			result,
			{
				"import_ok": False,
				"device": None,
				"metal_available": False,
				"mlx_version": None,
			},
		)


if __name__ == "__main__":
	unittest.main()
