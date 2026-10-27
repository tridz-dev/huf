import json
import sys

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways import teams_cards as c  # noqa: E402

SECRETISH = ("password", "secret", "token", "role", "price", "@", "api_key", "credential")
TYPES_ALLOWED = {"AdaptiveCard", "TextBlock", "FactSet", "Action.Execute"}


def walk(node):
	if isinstance(node, dict):
		yield node
		for v in node.values():
			yield from walk(v)
	elif isinstance(node, list):
		for v in node:
			yield from walk(v)


def approval(session="sess123"):
	return c.approval_card(session, "Approval requested", [("Kind", "code execution"), ("Capability", "run")])


def test_schema_and_version():
	card, _fb = approval()
	assert card["type"] == "AdaptiveCard"
	assert card["version"] == "1.5"
	assert card["$schema"] == "http://adaptivecards.io/schemas/adaptive-card.json"
	assert isinstance(card["body"], list) and card["body"]


def test_only_known_element_types():
	card, _ = approval()
	types = {n.get("type") for n in walk(card) if "type" in n}
	assert types <= TYPES_ALLOWED


def test_two_execute_actions_with_verbs():
	card, _ = approval()
	acts = card["actions"]
	assert [a["type"] for a in acts] == ["Action.Execute", "Action.Execute"]
	assert [a["verb"] for a in acts] == [c.VERB_APPROVE, c.VERB_REJECT]
	assert all(a["title"] for a in acts)


def test_action_data_is_only_session_name():
	card, _ = approval("abc999")
	for a in card["actions"]:
		assert a["data"] == {"session": "abc999"}


def test_card_has_no_secret_like_data():
	card, _ = approval()
	text = json.dumps(card).lower()
	for word in SECRETISH:
		assert word not in text.replace("approval requested", ""), word


def test_text_fallback_present_and_plain():
	_card, fb = approval()
	assert fb and "<" not in fb and "Approval requested" in fb


def test_activity_with_card_shape():
	card, fb = approval()
	act = c.activity_with_card(card, fb)
	assert act["type"] == "message" and act["text"] == fb
	att = act["attachments"][0]
	assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
	assert att["content"] is card


def test_clean_strips_control_chars_and_collapses():
	assert c.clean("a\x00b\x07 \n  c") == "ab c"


def test_clean_escapes_markdown():
	out = c.clean("[x](http://e) *b* `c` <t>")
	for ch in "[]()*`<>":
		assert "\\" + ch in out


def test_clean_bounds_length():
	assert len(c.clean("x" * 5000)) <= c.MAX_VALUE
	assert len(c.clean("x" * 5000, 10)) <= 10


def test_title_bounded():
	card, _ = c.approval_card("s", "T" * 1000)
	assert len(card["body"][0]["text"]) <= c.MAX_TITLE


def test_facts_bounded_and_skip_empty():
	facts = [(f"L{i}", f"v{i}") for i in range(30)] + [("Empty", ""), ("None", None)]
	card, _ = c.approval_card("s", "t", facts)
	rows = card["body"][1]["facts"]
	assert len(rows) <= c.MAX_FACTS
	assert all(r["value"] for r in rows)


def test_fact_value_hostile_text_escaped():
	card, _ = c.approval_card("s", "t", [("Ref", "[click](http://evil)")])
	assert "[click]" not in card["body"][1]["facts"][0]["value"]


def test_decided_card_has_no_actions():
	card, line = c.decided_card("Approved", "Ada", "2026-01-01 10:00:00")
	assert "actions" not in card
	assert "Approved by Ada" in line


def test_decided_card_escapes_name():
	card, _ = c.decided_card("Rejected", "*Evil*", "now")
	text = [b for b in card["body"] if b["type"] == "TextBlock"][1]["text"]
	assert "\\*Evil\\*" in text


def test_notice_card_bounded_no_actions():
	card, fb = c.notice_card("n" * 2000)
	assert "actions" not in card and len(fb) <= c.MAX_NOTICE


def test_invoke_card_response_shape():
	card, _ = c.notice_card("hi")
	resp = c.invoke_card_response(card)
	assert resp == {"statusCode": 200, "type": "application/vnd.microsoft.card.adaptive", "value": card}


def test_invoke_message_response_shape():
	resp = c.invoke_message_response("nope\x00")
	assert resp["statusCode"] == 200 and resp["type"] == "application/vnd.microsoft.activity.message"
	assert resp["value"] == "nope"


def test_cards_are_json_serialisable():
	for card in (approval()[0], c.notice_card("x")[0], c.decided_card("Approved", "a", "t")[0]):
		json.dumps(card)


@pytest.mark.parametrize("builder_args", [("s", "t", None), ("s", "", [])])
def test_approval_card_minimal_inputs(builder_args):
	card, fb = c.approval_card(*builder_args)
	assert card["actions"] and fb
