"""Flow realtime events never reach the site room and carry no raw error text."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.realtime import get_doc_room, get_site_room, get_user_room
from frappe.tests import UnitTestCase

from huf.ai.flow import engine

RUN = SimpleNamespace(name="FR-1", flow_id="journey", flow_definition="FD-1", owner="starter@example.com")


class TestFlowRealtimeScope(UnitTestCase):
	def _publish(self, data=None, run=RUN, allowed=True):
		with (
			patch.object(engine, "flow_access", return_value=allowed) as access,
			patch.object(frappe, "publish_realtime") as publish,
		):
			engine._publish_flow_event(run, "flow_error", data or {})
		self.access = access
		return [c.kwargs for c in publish.call_args_list]

	def test_goes_to_the_run_room_and_the_permitted_starter_only(self):
		calls = self._publish({"node_id": "a"})
		rooms = [c["room"] for c in calls]
		self.assertEqual(rooms, [get_doc_room("Agent Flow Run", "FR-1"), get_user_room(RUN.owner)])
		self.assertNotIn(get_site_room(), rooms)
		self.access.assert_called_once_with(RUN.owner, "FD-1", "view")

	def test_a_starter_without_view_access_gets_nothing_direct(self):
		calls = self._publish(allowed=False)
		self.assertEqual([c["room"] for c in calls], [get_doc_room("Agent Flow Run", "FR-1")])

	def test_a_guest_started_run_reaches_the_run_room_only(self):
		calls = self._publish(run=SimpleNamespace(**{**vars(RUN), "owner": "Guest"}))
		self.assertEqual([c["room"] for c in calls], [get_doc_room("Agent Flow Run", "FR-1")])

	def test_error_text_is_masked(self):
		calls = self._publish({"error": "ValueError: no reply from asha@example.com on +919812345678"})
		for call in calls:
			error = call["message"]["error"]
			self.assertNotIn("asha@example.com", error)
			self.assertNotIn("9812345678", error)
			self.assertNotIn("ValueError", error)
