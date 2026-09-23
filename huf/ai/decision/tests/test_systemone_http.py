"""Unit tests for the systemone HTTP transport (mocked HTTP layer, no network)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.decision.transports import build_transport as dispatch_build_transport
from huf.ai.decision.transports.systemone_http import build_transport


class URLValidationError(Exception):
	pass


def _provider(
	*,
	name="OpenCode Zen",
	provider_brand="opencode-zen",
	api_base_url=None,
	is_local_llm=False,
	timeout_seconds=180,
	api_key="secret-key",
):
	return SimpleNamespace(
		name=name,
		provider_brand=provider_brand,
		api_base_url=api_base_url,
		is_local_llm=is_local_llm,
		timeout_seconds=timeout_seconds,
		get_password=lambda field, raise_exception=False: api_key,
	)


def _deployment(
	*,
	provider="OpenCode Zen",
	provider_model_id="jev-1.13-free",
	wire_protocol="systemone",
	endpoint_path=None,
	latency_budget_ms=None,
	provider_metadata_json=None,
):
	return SimpleNamespace(
		provider=provider,
		provider_model_id=provider_model_id,
		wire_protocol=wire_protocol,
		endpoint_path=endpoint_path,
		latency_budget_ms=latency_budget_ms,
		provider_metadata_json=provider_metadata_json,
	)


class _Response:
	def __init__(self, status, body):
		self.status = status
		self._body = body

	def read(self):
		return json.dumps(self._body).encode("utf-8")

	def __enter__(self):
		return self

	def __exit__(self, *args):
		return False


class _RawResponse(_Response):
	"""Response whose body is not valid JSON."""

	def read(self):
		return self._body


class TestBuildTransportURLResolution(unittest.TestCase):
	def test_uses_provider_api_base_url_and_deployment_endpoint_path(self):
		provider = _provider(api_base_url="https://api.example.com")
		deployment = _deployment(endpoint_path="/custom/systemone")
		seen = {}

		def opener(request, timeout):
			seen["url"] = request.full_url
			return _Response(200, {"answers": {}})

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=10.0, opener=opener)
		transport({"model": "x"})
		self.assertEqual(seen["url"], "https://api.example.com/custom/systemone")

	def test_falls_back_to_catalog_brand_default_and_endpoint(self):
		provider = _provider(api_base_url=None, provider_brand="opencode-zen")
		deployment = _deployment(endpoint_path=None, provider_model_id="jev-1.13-free")
		seen = {}

		def opener(request, timeout):
			seen["url"] = request.full_url
			return _Response(200, {"answers": {}})

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=10.0, opener=opener)
		transport({"model": "x"})
		self.assertEqual(seen["url"], "https://opencode.ai/zen/v1/systemone")

	def test_raises_when_no_base_url_resolvable(self):
		# No catalog entry for this brand/model and no api_base_url.
		provider = _provider(api_base_url=None, provider_brand="unknown-brand")
		deployment = _deployment(provider_model_id="does-not-exist")
		with patch("frappe.get_doc", return_value=provider):
			with self.assertRaises(ValueError):
				build_transport(deployment, timeout=10.0)


class TestBuildTransportSecurity(unittest.TestCase):
	def test_private_host_rejected_by_default(self):
		provider = _provider(api_base_url="https://192.168.1.5", is_local_llm=False)
		deployment = _deployment()
		with patch("frappe.get_doc", return_value=provider), patch(
			"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
		):
			with self.assertRaises(URLValidationError):
				build_transport(deployment, timeout=10.0)

	def test_private_host_allowed_when_provider_is_local_llm(self):
		provider = _provider(api_base_url="http://192.168.1.5:11434", is_local_llm=True)
		deployment = _deployment(endpoint_path="/v1/systemone")

		def opener(request, timeout):
			return _Response(200, {"answers": {}})

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=10.0, opener=opener)
		status, body = transport({"model": "x"})
		self.assertEqual(status, 200)

	def test_missing_api_key_raises(self):
		provider = _provider(api_key=None)
		deployment = _deployment()
		with patch("frappe.get_doc", return_value=provider):
			with self.assertRaises(ValueError):
				build_transport(deployment, timeout=10.0)

	def test_api_key_never_appears_in_error_response_body(self):
		provider = _provider(api_key="super-secret-value")
		deployment = _deployment()

		def opener(request, timeout):
			from urllib.error import HTTPError

			raise HTTPError(request.full_url, 401, "Unauthorized: super-secret-value", None, None)

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=10.0, opener=opener)
		status, body = transport({"model": "x"})
		self.assertEqual(status, 401)
		self.assertNotIn("super-secret-value", json.dumps(body))

	def test_authorization_header_carries_the_key_but_payload_never_logs_it(self):
		provider = _provider(api_key="bearer-secret")
		deployment = _deployment()
		seen = {}

		def opener(request, timeout):
			seen["auth"] = request.get_header("Authorization")
			return _Response(200, {"answers": {}})

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=10.0, opener=opener)
		transport({"model": "x"})
		self.assertEqual(seen["auth"], "Bearer bearer-secret")


class TestBuildTransportResponses(unittest.TestCase):
	def _transport(self, opener, **deployment_kwargs):
		provider = _provider()
		deployment = _deployment(**deployment_kwargs)
		with patch("frappe.get_doc", return_value=provider):
			return build_transport(deployment, timeout=10.0, opener=opener)

	def test_200_success(self):
		transport = self._transport(lambda request, timeout: _Response(200, {"answers": {"q1": {"noul": 0.5}}}))
		status, body = transport({"model": "x"})
		self.assertEqual(status, 200)
		self.assertEqual(body, {"answers": {"q1": {"noul": 0.5}}})

	def test_401_no_retry(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			from urllib.error import HTTPError

			raise HTTPError(request.full_url, 401, "Unauthorized", None, None)

		transport = self._transport(opener)
		status, body = transport({"model": "x"})
		self.assertEqual(status, 401)
		self.assertEqual(body, {})
		self.assertEqual(len(calls), 1)

	def test_429_never_retried(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			from urllib.error import HTTPError

			raise HTTPError(request.full_url, 429, "Too Many Requests", None, None)

		transport = self._transport(opener)
		status, body = transport({"model": "x"})
		self.assertEqual(status, 429)
		self.assertEqual(body, {})
		self.assertEqual(len(calls), 1, "429 must never be retried by the transport")

	def test_5xx_retried_with_backoff_then_fails(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			from urllib.error import HTTPError

			raise HTTPError(request.full_url, 503, "Service Unavailable", None, None)

		with patch("time.sleep") as mock_sleep:
			transport = self._transport(opener)
			status, body = transport({"model": "x"})
		self.assertEqual(status, 503)
		self.assertEqual(body, {})
		# Default max_retries=2 => 1 initial attempt + 2 retries = 3 calls.
		self.assertEqual(len(calls), 3)
		self.assertEqual(mock_sleep.call_count, 2)

	def test_5xx_retried_then_succeeds(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			if len(calls) < 2:
				from urllib.error import HTTPError

				raise HTTPError(request.full_url, 500, "Internal Server Error", None, None)
			return _Response(200, {"answers": {}})

		with patch("time.sleep"):
			transport = self._transport(opener)
			status, body = transport({"model": "x"})
		self.assertEqual(status, 200)
		self.assertEqual(len(calls), 2)

	def test_max_retries_from_provider_metadata_json(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			from urllib.error import HTTPError

			raise HTTPError(request.full_url, 500, "Internal Server Error", None, None)

		with patch("time.sleep"):
			transport = self._transport(opener, provider_metadata_json=json.dumps({"max_retries": 0}))
			status, body = transport({"model": "x"})
		self.assertEqual(status, 500)
		self.assertEqual(len(calls), 1, "max_retries=0 means no retries")

	def test_timeout_raises_timeout_error(self):
		def opener(request, timeout):
			raise TimeoutError("timed out")

		transport = self._transport(opener)
		with self.assertRaises(TimeoutError):
			transport({"model": "x"})

	def test_timeout_wrapped_in_urlerror_still_raises_timeout_error(self):
		def opener(request, timeout):
			from urllib.error import URLError

			raise URLError(TimeoutError("timed out"))

		transport = self._transport(opener)
		with self.assertRaises(TimeoutError):
			transport({"model": "x"})

	def test_connection_error_raises(self):
		def opener(request, timeout):
			from urllib.error import URLError

			raise URLError("connection refused")

		transport = self._transport(opener)
		with self.assertRaises(ConnectionError):
			transport({"model": "x"})

	def test_bad_json_body_on_success_returns_empty_mapping(self):
		transport = self._transport(lambda request, timeout: _RawResponse(200, b"not json {{{"))
		status, body = transport({"model": "x"})
		self.assertEqual(status, 200)
		self.assertEqual(body, {})


class TestResolveTimeout(unittest.TestCase):
	def test_effective_timeout_is_min_of_budget_and_provider_timeout(self):
		provider = _provider(timeout_seconds=5)
		deployment = _deployment(latency_budget_ms=None)
		seen = {}

		def opener(request, timeout):
			seen["timeout"] = timeout
			return _Response(200, {"answers": {}})

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=30.0, opener=opener)
		transport({"model": "x"})
		self.assertEqual(seen["timeout"], 5)

	def test_effective_timeout_narrowed_by_latency_budget_ms(self):
		provider = _provider(timeout_seconds=180)
		deployment = _deployment(latency_budget_ms=2000)
		seen = {}

		def opener(request, timeout):
			seen["timeout"] = timeout
			return _Response(200, {"answers": {}})

		with patch("frappe.get_doc", return_value=provider):
			transport = build_transport(deployment, timeout=30.0, opener=opener)
		transport({"model": "x"})
		self.assertEqual(seen["timeout"], 2.0)


class TestDispatchBuildTransport(unittest.TestCase):
	"""huf.ai.decision.transports.build_transport dispatch on wire_protocol."""

	def test_dispatches_systemone_to_http_transport(self):
		provider = _provider()
		deployment = _deployment(wire_protocol="systemone")
		with patch("frappe.get_doc", return_value=provider):
			transport = dispatch_build_transport(deployment, timeout=10.0)
		self.assertTrue(callable(transport))

	def test_openai_chat_json_raises_not_implemented(self):
		deployment = _deployment(wire_protocol="openai_chat_json")
		with self.assertRaises(NotImplementedError):
			dispatch_build_transport(deployment, timeout=10.0)

	def test_unknown_wire_protocol_raises_value_error(self):
		deployment = _deployment(wire_protocol="carrier-pigeon")
		with self.assertRaises(ValueError):
			dispatch_build_transport(deployment, timeout=10.0)


if __name__ == "__main__":
	unittest.main()
