# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Send-time member recipient (H-W2-26): ``$member`` fails closed (G5), the number is never stored (G4),
delivery re-resolves it, and template params are positional in slot order unless the template is NAMED."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import guard, guard_steps, outbox, recipient_binder, token_binder
from huf.ai.channels.recipient_binder import RECIPIENT_UNBOUND, RecipientUnbound
from huf.ai.flow import engine, preflight
from huf.ai.flow.nodes import send
from huf.ai.flow.support import reason_codes, step_keys
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.graph.executor import GraphContext
from huf.ai.whatsapp import management

PHONE = "+15550009876"
PHONE_DIGITS = "15550009876"
NEW_PHONE = "+15550004321"
MEMBER = "m-rcpt-1"
CTX = {"flow_id": "f", "flow_version": "1", "run_id": "r", "node_id": "n", "extra": "dropped"}
NODE = {"id": "s1", "type": "send.message", "next": "n2"}
CONFIG = {"gateway": "gw", "recipient": "$member", "template": "promo", "category": "service"}


def answering(mapping):
	return lambda gateway, members, context: {m: mapping[m] for m in members if m in mapping}


def failing(gateway, members, context):
	raise ValueError(PHONE)


class ProviderMixin:
	def providers(self, *providers):
		registry = {f"app.recipient{i}": p for i, p in enumerate(providers)}
		get_hooks, get_attr = frappe.get_hooks, frappe.get_attr
		patch.object(
			frappe,
			"get_hooks",
			side_effect=lambda hook=None, *a, **k: (
				list(registry) if hook == recipient_binder.HOOK else get_hooks(hook, *a, **k)
			),
		).start()
		patch.object(
			frappe,
			"get_attr",
			side_effect=lambda path: registry[path] if path in registry else get_attr(path),
		).start()
		return registry


class TestRecipientBinder(ProviderMixin, IntegrationTestCase):
	def setUp(self):
		patch.object(frappe, "logger").start()
		self.addCleanup(patch.stopall)

	def test_resolves_first_str_and_passes_four_context_keys(self):
		seen = []

		def first(gateway, members, context):
			seen.append(context)
			return {}

		self.providers(first, answering({MEMBER: PHONE}), answering({MEMBER: NEW_PHONE}))
		self.assertEqual(recipient_binder.resolve("gw", MEMBER, CTX), PHONE)
		self.assertEqual(set(seen[0]), set(recipient_binder.CONTEXT_KEYS))

	def test_every_miss_blocks_recipient_unbound(self):
		cases = {
			"no provider": (),
			"omits member": (answering({}),),
			"raises": (failing,),
			"not a dict": (lambda g, m, c: [PHONE],),
			"non-str": (lambda g, m, c: {MEMBER: 15550009876},),
			"blank": (answering({MEMBER: "  "}),),
		}
		for label, providers in cases.items():
			with self.subTest(label):
				patch.stopall()
				patch.object(frappe, "logger").start()
				self.providers(*providers)
				with self.assertRaises(RecipientUnbound) as raised:
					recipient_binder.resolve("gw", MEMBER, CTX)
				self.assertEqual(raised.exception.code, RECIPIENT_UNBOUND)
				self.assertNotIn(PHONE, str(raised.exception))
		with self.assertRaises(RecipientUnbound):
			recipient_binder.resolve("gw", None, CTX)

	def test_reason_code_registered(self):
		self.assertIn(RECIPIENT_UNBOUND, reason_codes.HUF_CODES)


class TestMemberSend(ProviderMixin, IntegrationTestCase):
	def setUp(self):
		self.requests = []
		self.enqueue = MagicMock(return_value=None)
		patch.object(frappe, "logger").start()
		patch.object(guard, "BUILTIN_STEPS", [("record", self._record)]).start()
		patch.object(guard, "_hook_paths", return_value=[]).start()
		patch.object(guard_steps, "window_resolvers", return_value=[]).start()
		patch.object(guard_steps, "resolve_caps", return_value=[]).start()
		patch.object(send, "_enqueue", self.enqueue).start()
		patch.object(send, "channel_of", return_value="whatsapp").start()
		patch("huf.ai.flow.testrun.gate.live_send_on", return_value=True).start()
		patch("huf.ai.flow.testrun.gate.pin_is_current", return_value=True).start()
		self.ctx = GraphContext()
		patch.object(engine, "_context_of", return_value=self.ctx).start()
		patch.object(engine, "_persist_context").start()
		patch.object(engine, "_transition_run", return_value=True).start()
		self.addCleanup(patch.stopall)

	def _record(self, request):
		self.requests.append(request)
		return {"allow": True}

	def run_node(self, member_key=MEMBER):
		flow_run = SimpleNamespace(
			name="RUN-R1",
			flow_id="flow-1",
			flow_version="3",
			member_key=member_key,
			run_mode="",
			status="Running",
			waiting=None,
		)
		node = step_keys.with_key(NODE, frappe.generate_hash())
		return send.exec_send_message(flow_run, node, dict(CONFIG), {})

	def test_member_resolved_for_guard_but_only_ref_queued(self):
		self.providers(answering({MEMBER: PHONE}))
		result = self.run_node()
		self.assertEqual(result["output"], {"status": "queued"})
		self.assertEqual(self.requests[0]["recipient"], PHONE)
		queued = self.enqueue.call_args.args[0]
		self.assertEqual(queued["recipient_ref"], "$member")
		for where in (frappe.as_json(result), frappe.as_json(self.ctx.data), frappe.as_json(queued)):
			self.assertNotIn(PHONE_DIGITS, where)

	def test_unbound_blocks_before_guard_and_nothing_queued(self):
		for label, providers, member in (
			("no provider", (), MEMBER),
			("omits", (answering({}),), MEMBER),
			("raises", (failing,), MEMBER),
			("no member_key", (answering({MEMBER: PHONE}),), None),
		):
			with self.subTest(label):
				self.requests.clear()
				self.enqueue.reset_mock()
				registry = self.providers(*providers)
				result = self.run_node(member)
				self.assertEqual(result["output"], {"status": "blocked", "reason": RECIPIENT_UNBOUND})
				self.assertEqual(self.requests, [])
				self.enqueue.assert_not_called()
				self.assertNotIn(PHONE_DIGITS, frappe.as_json(result) + frappe.as_json(self.ctx.data))
				registry.clear()

	def test_preflight_accepts_member_ref(self):
		self.assertIsNone(send.config_problem(dict(CONFIG)))
		with (
			patch.object(preflight, "gateway_channel", return_value="whatsapp"),
			patch.object(preflight, "template_exists", return_value=True),
		):
			found = preflight._send_checks({"nodes": [{**NODE, "config": dict(CONFIG)}]}, None)
		self.assertNotIn("SEND_RECIPIENT_LITERAL", [f.code for f in found])
		self.assertNotIn("SEND_GUARD_CONFIG_MISSING", [f.code for f in found])


class TestMemberDelivery(ProviderMixin, IntegrationTestCase):
	def setUp(self):
		patch.object(frappe, "logger").start()
		patch.object(frappe.db, "commit").start()
		self.bound_ctx = []
		patch.object(
			token_binder,
			"bind",
			side_effect=lambda t, n, m, c: self.bound_ctx.append(c) or {x: "v" for x in n},
		).start()
		run = SimpleNamespace(name="RUN-D1", flow_id="flow-d", flow_version="7")
		get_doc = frappe.get_doc
		patch.object(
			frappe,
			"get_doc",
			side_effect=lambda *a, **k: run if a and a[0] == "Agent Flow Run" else get_doc(*a, **k),
		).start()
		patch.object(engine, "_context_of", return_value=GraphContext()).start()
		self.sent = []
		self.addCleanup(patch.stopall)

	def transport(self, row, recipient, text, values):
		self.sent.append(recipient)
		return {"message_id": "wamid." + row.step_key}

	def queue(self, **over):
		return outbox.enqueue(
			{
				"step_key": "sk-" + frappe.generate_hash(length=10),
				"run_id": "RUN-D1",
				"node_id": "send1",
				"member_key": MEMBER,
				"channel": "whatsapp",
				"category": "service",
				"template": "t",
				"recipient_ref": "$member",
				"token_names": ["1"],
				**over,
			},
			deliver_now=False,
		)

	def test_delivery_re_resolves_and_row_never_holds_number(self):
		number = {MEMBER: PHONE}
		self.providers(lambda g, m, c: {k: number[k] for k in m if k in number})
		name = self.queue()
		number[MEMBER] = NEW_PHONE  # the member changed their mobile between queue and delivery
		self.assertEqual(outbox.deliver(name, transport=self.transport), "Sent")
		self.assertEqual(self.sent, [NEW_PHONE])
		row = frappe.get_doc(outbox.DOCTYPE, name)
		self.assertEqual(row.recipient_ref, "$member")
		self.assertNotIn("1555000", frappe.as_json(row.as_dict()))
		self.assertEqual(self.bound_ctx[0]["run_id"], "RUN-D1")
		self.assertEqual(self.bound_ctx[0]["node_id"], "send1")
		self.assertEqual(set(self.bound_ctx[0]), set(token_binder.CONTEXT_KEYS))

	def test_unbound_at_delivery_is_final_blocked(self):
		self.providers(answering({}))
		name = self.queue()
		self.assertEqual(outbox.deliver(name, transport=self.transport), "Blocked")
		self.assertEqual(self.sent, [])
		row = frappe.get_doc(outbox.DOCTYPE, name)
		self.assertEqual((row.error_class, row.error_code), (outbox.BLOCKED, RECIPIENT_UNBOUND))


SLOT_NAMES = ["lit_1", "points_earned", "business_name"] + [f"lit_{i}" for i in range(4, 11)]
SLOT_VALUES = {name: f"v-{name}" for name in SLOT_NAMES}


class TestBodyParams(IntegrationTestCase):

	def test_positional_is_list_in_slot_order_not_sorted(self):
		params = send._body_params(SLOT_NAMES, SLOT_VALUES)
		self.assertEqual(params, [SLOT_VALUES[n] for n in SLOT_NAMES])
		self.assertEqual(params[9], "v-lit_10")  # slot 10 after slot 9, never "10" before "2"
		digits = [str(i) for i in range(1, 11)]
		self.assertEqual(send._body_params(digits, {d: d for d in digits}), digits)

	def test_named_is_map(self):
		self.assertEqual(
			send._body_params(["first_name"], {"first_name": "Sam"}, named=True), {"first_name": "Sam"}
		)

	def test_transport_detects_format_from_template(self):
		row = SimpleNamespace(
			channel="whatsapp",
			gateway="gw",
			template="tpl",
			token_names='["first_name", "points_earned"]',  # noqa: S106
			header=None,
			language=None,
			run_id="r",
		)
		values = {"first_name": "Sam", "points_earned": "40"}
		for fmt, expected in (
			("NAMED", values),
			("POSITIONAL", ["Sam", "40"]),
			("", ["Sam", "40"]),
		):
			with (
				self.subTest(fmt),
				patch.object(bridge, "_template_row", return_value={"parameter_format": fmt}),
				patch.object(bridge, "send_template", return_value={"message_id": "x"}) as send_template,
				patch.object(management, "_send_authority", return_value=None),
			):
				outbox.whatsapp_transport(row, PHONE, None, values)
				self.assertEqual(send_template.call_args.args[3], expected)
		with patch.object(bridge, "_template_row", return_value=None):
			self.assertFalse(outbox.template_is_named("missing"))
