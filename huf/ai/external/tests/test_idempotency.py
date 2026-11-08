# ruff: noqa: S101
from __future__ import annotations

from huf.ai.external.idempotency import args_hash, canonical_json, make_idempotency_key


def test_dict_key_order_does_not_change_key():
	a = {"x": 1, "y": {"b": 2, "a": 3}}
	b = {"y": {"a": 3, "b": 2}, "x": 1}
	assert canonical_json(a) == canonical_json(b)
	assert args_hash(a) == args_hash(b)
	assert make_idempotency_key("s1", "t", a) == make_idempotency_key("s1", "t", b)


def test_different_inputs_produce_different_keys():
	base = make_idempotency_key("s1", "tool", {"a": 1}, "c1")
	assert make_idempotency_key("s1", "tool", {"a": 2}, "c1") != base
	assert make_idempotency_key("s1", "other", {"a": 1}, "c1") != base
	assert make_idempotency_key("s2", "tool", {"a": 1}, "c1") != base
	assert make_idempotency_key("s1", "tool", {"a": 1}, "c2") != base
	assert make_idempotency_key("s1", "tool", {"a": 1}, None) != base


def test_separator_characters_in_values_do_not_collide():
	# Joining raw parts with "|" would make these two different calls produce the same input.
	pipe_in_session = make_idempotency_key("a|b", "c", None)
	pipe_in_tool = make_idempotency_key("a", "b|c", None)
	assert pipe_in_session != pipe_in_tool


def test_none_args_equals_empty_dict_hash():
	assert args_hash(None) == args_hash({})
	assert make_idempotency_key("s", "t", None) == make_idempotency_key("s", "t", {})


def test_output_is_deterministic_sha256_hex():
	key = make_idempotency_key("s", "t", {"k": "v"}, "call-1")
	assert len(key) == 64
	assert key == make_idempotency_key("s", "t", {"k": "v"}, "call-1")
	assert len(args_hash({"k": "v"})) == 64
	int(key, 16)
