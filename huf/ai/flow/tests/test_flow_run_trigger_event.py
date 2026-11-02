"""The document event shown in Run details comes from the (pinned) data trigger of the run's flow.

  python -m pytest huf/ai/flow/tests/test_flow_run_trigger_event.py   (no bench needed: the definition is pinned on the run)
"""

import json
import unittest
from types import SimpleNamespace

from huf.ai.flow import api as flow_api


def _run(definition, trigger_type="Doc Event"):
	return SimpleNamespace(trigger_type=trigger_type, pinned_definition=json.dumps(definition) if definition is not None else None, flow_id="f")


def _graph(*triggers):
	return {"nodes": [{"id": f"t{i}", "type": "trigger.doc-event", "config": c} for i, c in enumerate(triggers)]}


class TestTriggerEvent(unittest.TestCase):
	def test_reads_event_from_graph_wrapped_in_pinned_definition(self):
		run = _run({"fingerprint": "x", "graph": _graph({"doctype": "ToDo", "event": "on_trash"})})
		self.assertEqual(flow_api._trigger_event(run, {"doctype": "ToDo"}), "on_trash")

	def test_picks_the_trigger_for_the_documents_doctype(self):
		run = _run(_graph({"doctype": "ToDo", "event": "after_insert"}, {"doctype": "Note", "event": "on_update"}))
		self.assertEqual(flow_api._trigger_event(run, {"doctype": "Note"}), "on_update")

	def test_other_triggers_have_no_event(self):
		self.assertIsNone(flow_api._trigger_event(_run(_graph({"doctype": "ToDo", "event": "on_trash"}), "Webhook"), {}))
