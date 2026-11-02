"""JSON-structure checks for the Solutions schema (no database needed)."""

import json
import unittest
from pathlib import Path

DOCTYPE_DIR = Path(__file__).resolve().parents[3] / "huf" / "doctype"
NEW = ["solution", "conversation_assignment", "template_usage"]
LAYOUT = {"Section Break", "Column Break", "Tab Break"}

# doctype dir -> fields that must exist
EXPECTED = {
    "solution": ["title", "purpose", "status", "test_mode", "description", "solution_owner",
                 "primary_target_type", "primary_agent", "primary_flow"],
    "conversation_assignment": ["gateway", "contact", "solution", "expires_at", "set_by",
                                "source_binding", "triage_pending_until"],
    "template_usage": ["whatsapp_account", "template", "language", "solution", "kind", "source"],
    "gateway_binding": ["solution", "cap_per_day", "scope_override", "allow_first_message"],
    "gateway": ["pin_ttl_hours", "keyword_beats_pin"],
    "agent": ["solution"],
    "flow_definition": ["solution"],
    "gateway_event": ["solution"],
    "agent_run": ["solution"],
    "agent_conversation": ["solution"],
    "whatsapp_send_key": ["solution"],
}
READ_ONLY = ["gateway_event", "agent_run", "agent_conversation", "whatsapp_send_key"]


def load(snake):
    return json.loads((DOCTYPE_DIR / snake / f"{snake}.json").read_text())


def fields_by_name(meta):
    return {f["fieldname"]: f for f in meta["fields"]}


class TestSchemaFields(unittest.TestCase):
    def test_expected_fields_exist(self):
        for snake, names in EXPECTED.items():
            by = fields_by_name(load(snake))
            for n in names:
                self.assertIn(n, by, f"{snake}.{n} missing")

    def test_field_order_consistent(self):
        for snake in EXPECTED:
            meta = load(snake)
            order = meta["field_order"]
            self.assertEqual(len(order), len(set(order)), f"{snake} field_order has duplicates")
            names = {f["fieldname"] for f in meta["fields"]}
            self.assertEqual(len(names), len(meta["fields"]), f"{snake} duplicate fieldnames")
            self.assertFalse(names - set(order), f"{snake} fields missing from field_order")
            self.assertFalse(set(order) - names, f"{snake} field_order has unknown fields")

    def test_new_doctypes_link_only_huf_doctypes(self):
        huf_doctypes = {load(p.name)["name"] for p in DOCTYPE_DIR.iterdir()
                        if (p / f"{p.name}.json").exists()}
        for snake in NEW:
            for f in load(snake)["fields"]:
                if f["fieldtype"] == "Link":
                    target = f["options"]
                    if target in ("User", "Role"):
                        continue
                    self.assertIn(target, huf_doctypes, f"{snake}.{f['fieldname']} -> {target}")

    def test_solution_links_target_solution(self):
        for snake, names in EXPECTED.items():
            if "solution" in names and snake not in NEW:
                f = fields_by_name(load(snake))["solution"]
                self.assertEqual((f["fieldtype"], f["options"]), ("Link", "Solution"))
        for snake in READ_ONLY:
            self.assertTrue(fields_by_name(load(snake))["solution"].get("read_only"))
        for snake in ("agent", "flow_definition"):
            self.assertFalse(fields_by_name(load(snake))["solution"].get("read_only"))

    def test_whatsapp_account_is_data(self):
        self.assertEqual(fields_by_name(load("template_usage"))["whatsapp_account"]["fieldtype"], "Data")

    def test_binding_options_append_only(self):
        by = fields_by_name(load("gateway_binding"))
        mt = by["match_type"]["options"].split("\n")
        self.assertEqual(mt[:5], ["Any conversation", "Direct message", "Room or channel", "Thread", "Sender"])
        for o in ("Keyword", "Ad or link tag", "Catch-all"):
            self.assertIn(o, mt)
        tt = by["target_type"]["options"].split("\n")
        self.assertEqual(tt[:2], ["Agent", "Flow"])
        self.assertIn("Triage", tt)

    def test_gateway_defaults(self):
        by = fields_by_name(load("gateway"))
        self.assertEqual(by["pin_ttl_hours"]["default"], "24")
        self.assertEqual(by["keyword_beats_pin"]["default"], "0")

    def test_permissions_and_autoname(self):
        for snake in NEW:
            meta = load(snake)
            self.assertEqual(meta["autoname"], "hash")
            self.assertEqual([p["role"] for p in meta["permissions"]], ["System Manager"])
