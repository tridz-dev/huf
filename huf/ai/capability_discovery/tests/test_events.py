# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json
import os

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.capabilities.events import (
    ADVANCED_EVENT_LABELS,
    CANONICAL_EVENT_LABELS,
    build_trigger_payload,
    generate_events_for_resource,
)


def _agent_trigger_doc_event_options():
    """Read the real `doc_event` Select options straight out of
    huf/huf/doctype/agent_trigger/agent_trigger.json, so this test stays
    honest against the actual doctype definition instead of a hardcoded
    copy that could drift.
    """
    json_path = frappe.get_app_path("huf", "huf", "doctype", "agent_trigger", "agent_trigger.json")
    with open(json_path) as f:
        doctype_def = json.load(f)

    for field in doctype_def["fields"]:
        if field.get("fieldname") == "doc_event":
            options = field["options"].split("\n")
            return {opt for opt in options if opt}

    raise AssertionError("doc_event field not found in agent_trigger.json")


class TestCanonicalEventLabels(IntegrationTestCase):
    def test_canonical_events_map_to_real_doc_event_options(self):
        real_options = _agent_trigger_doc_event_options()

        for human_label, technical_event in CANONICAL_EVENT_LABELS.items():
            self.assertIn(
                technical_event,
                real_options,
                f"CANONICAL_EVENT_LABELS[{human_label!r}] = {technical_event!r} is not a "
                "valid Agent Trigger doc_event Select option",
            )

    def test_advanced_events_map_to_real_doc_event_options(self):
        real_options = _agent_trigger_doc_event_options()

        for technical_event, human_label in ADVANCED_EVENT_LABELS.items():
            self.assertIn(
                technical_event,
                real_options,
                f"ADVANCED_EVENT_LABELS[{technical_event!r}] ({human_label!r}) is not a "
                "valid Agent Trigger doc_event Select option",
            )


class TestGenerateEventsForResource(IntegrationTestCase):
    def test_non_submittable_excludes_submitted_and_cancelled(self):
        descriptors = generate_events_for_resource("huf", "ToDo", submittable=False)

        technical_events = {d["event_name"] for d in descriptors}
        self.assertNotIn(CANONICAL_EVENT_LABELS["Submitted"], technical_events)
        self.assertNotIn(CANONICAL_EVENT_LABELS["Cancelled"], technical_events)

        # The remaining canonical events should still be present.
        self.assertIn(CANONICAL_EVENT_LABELS["Created"], technical_events)
        self.assertIn(CANONICAL_EVENT_LABELS["Changed"], technical_events)
        self.assertIn(CANONICAL_EVENT_LABELS["Deleted"], technical_events)

    def test_submittable_includes_submitted_and_cancelled(self):
        descriptors = generate_events_for_resource("huf", "Sales Invoice", submittable=True)

        technical_events = {d["event_name"] for d in descriptors}
        self.assertIn(CANONICAL_EVENT_LABELS["Submitted"], technical_events)
        self.assertIn(CANONICAL_EVENT_LABELS["Cancelled"], technical_events)

    def test_include_advanced_adds_advanced_event_labels(self):
        without_advanced = generate_events_for_resource("huf", "ToDo", include_advanced=False)
        with_advanced = generate_events_for_resource("huf", "ToDo", include_advanced=True)

        without_events = {d["event_name"] for d in without_advanced}
        with_events = {d["event_name"] for d in with_advanced}

        # No advanced events should leak in when include_advanced=False.
        for technical_event in ADVANCED_EVENT_LABELS:
            self.assertNotIn(technical_event, without_events)

        # All advanced events should be present when include_advanced=True.
        for technical_event in ADVANCED_EVENT_LABELS:
            self.assertIn(technical_event, with_events)

        # Advanced descriptors are strictly additive on top of the canonical set.
        self.assertTrue(with_events.issuperset(without_events))


class TestBuildTriggerPayload(IntegrationTestCase):
    def test_returns_expected_payload_keys(self):
        capability_id = "event:huf:ToDo.after_insert"

        payload = build_trigger_payload(
            "huf",
            "ToDo",
            capability_id,
            condition="doc.status == 'Open'",
            prompt_field="description",
        )

        self.assertEqual(
            set(payload.keys()),
            {"trigger_type", "reference_doctype", "doc_event", "condition", "prompt_field"},
        )
        self.assertEqual(payload["trigger_type"], "Doc Event")
        self.assertEqual(payload["reference_doctype"], "ToDo")
        self.assertEqual(payload["doc_event"], "after_insert")
        self.assertEqual(payload["condition"], "doc.status == 'Open'")
        self.assertEqual(payload["prompt_field"], "description")

    def test_raises_when_doctype_does_not_match_capability_id(self):
        capability_id = "event:huf:ToDo.after_insert"

        with self.assertRaises(frappe.ValidationError):
            build_trigger_payload("huf", "Sales Invoice", capability_id)
