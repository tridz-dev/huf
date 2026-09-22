import json
import unittest
from types import SimpleNamespace

from huf.ai.decision.backends.jev import opencode_zen_transport_from_env


class TestOpenCodeTransport(unittest.TestCase):
	def test_requires_key_without_network_call(self):
		with self.assertRaises(RuntimeError):
			opencode_zen_transport_from_env(api_key="")

	def test_sends_bearer_key_and_decodes_response(self):
		seen = {}
		class Response:
			status = 200
			def read(self): return json.dumps({"answers": {}}).encode()
			def __enter__(self): return self
			def __exit__(self, *args): return False
		def opener(request, timeout):
			seen["auth"] = request.get_header("Authorization")
			seen["timeout"] = timeout
			return Response()
		result = opencode_zen_transport_from_env(api_key="test-key", opener=opener)( {"model": "jev-1.13-free"} )
		self.assertEqual(result[0], 200)
		self.assertEqual(seen, {"auth": "Bearer test-key", "timeout": 30.0})
