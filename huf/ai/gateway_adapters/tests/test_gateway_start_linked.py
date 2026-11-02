"""START clears the opt-out under every linked sender id (found in live verification)."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai import gateway_service as gs


class TestStartClearsLinkedOptOut(unittest.TestCase):
	def test_start_opts_in_phone_and_bsuid(self):
		gateway = SimpleNamespace(name="GW", provider="WhatsApp")
		with (
			patch.object(gs, "_linked_sender_ids", return_value=["919876543210", "IN.4608123"]),
			patch.object(gs, "_record_opt_in") as opt_in,
		):
			gs._record_opt_in_linked(gateway, "919876543210")
		self.assertEqual([c.args[1] for c in opt_in.call_args_list], ["919876543210", "IN.4608123"])
