"""Focused validation checks for decision policies and provider-visible state."""

from __future__ import annotations

import hashlib
import unittest

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.policy import policy_fingerprint, validate_policy, validate_policy_data
from huf.ai.decision.state import prepare_state
from huf.ai.decision.types import (
	DecisionCapabilities,
	DecisionPolicy,
	DecisionRequest,
	Option,
	Question,
	QuestionKind,
	StateBinding,
)


def _question() -> Question:
	return Question(
		id="route",
		kind=QuestionKind.SELECT,
		instructions="Choose a route",
		options=(Option("billing"), Option("shipping")),
	)


def _policy(**kwargs) -> DecisionPolicy:
	kwargs.setdefault("state_bindings", (StateBinding("request", "$"),))
	return DecisionPolicy(policy_id="routing", questions=(_question(),), **kwargs)


class TestPolicyValidation(unittest.TestCase):
	def test_fingerprint_is_stable_and_tracks_policy_semantics(self):
		first = _policy(required_modalities=frozenset({"text", "image"}))
		second = _policy(required_modalities=frozenset({"image", "text"}))

		self.assertEqual(policy_fingerprint(first), policy_fingerprint(second))
		self.assertEqual(validate_policy(first).fingerprint, policy_fingerprint(first))
		self.assertNotEqual(
			policy_fingerprint(first),
			policy_fingerprint(_policy(version="2")),
		)

	def test_policy_data_rejects_unknown_and_executable_fields(self):
		base = {
			"policy_id": "routing",
			"questions": [{
				"id": "route",
				"kind": "select",
				"instructions": "Choose a route",
				"options": [{"id": "billing"}, {"id": "shipping"}],
			}],
		}
		invalid_definitions = (
			{**base, "unknown": True},
			{**base, "expression": "__import__('os').system('echo unsafe')"},
			{
				**base,
				"questions": [{**base["questions"][0], "callable": "run"}],
			},
		)

		for definition in invalid_definitions:
			with self.subTest(definition=definition):
				with self.assertRaises(DecisionError) as raised:
					validate_policy_data(definition)
				self.assertEqual(raised.exception.code, DecisionErrorCode.POLICY_INVALID)


class TestStatePreparation(unittest.TestCase):
	def test_state_bindings_project_only_selected_fields(self):
		policy = _policy(state_bindings=(StateBinding("request", "request"),))
		request = DecisionRequest(
			policy=policy,
			state={"request": "Please route this", "private_notes": "internal only"},
		)
		prepared = prepare_state(
			request,
			policy,
			DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT})),
		)

		self.assertEqual(prepared.value, {"request": "Please route this"})
		self.assertEqual(prepared.canonical_json, '{"request":"Please route this"}')
		self.assertNotIn("private_notes", prepared.canonical_json)

	def test_state_uses_canonical_json_sha256_and_utf8_size(self):
		state = {"z": "café", "a": [2, 1]}
		request = DecisionRequest(policy=_policy(), state=state)
		prepared = prepare_state(
			request,
			request.policy,
			DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT})),
		)
		projected = {"request": state}
		canonical = '{"request":{"a":[2,1],"z":"café"}}'
		self.assertEqual(prepared.value, projected)
		self.assertEqual(prepared.canonical_json, canonical)
		self.assertEqual(prepared.size_bytes, len(canonical.encode("utf-8")))
		self.assertEqual(prepared.sha256, hashlib.sha256(canonical.encode("utf-8")).hexdigest())

	def test_state_over_limit_is_rejected(self):
		policy = _policy(max_state_bytes=5)
		request = DecisionRequest(policy=policy, state={"x": 1})

		with self.assertRaises(DecisionError) as raised:
			prepare_state(
				request,
				policy,
				DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT})),
			)
		self.assertEqual(raised.exception.code, DecisionErrorCode.STATE_TOO_LARGE)

	def test_unsupported_modality_is_rejected(self):
		policy = _policy()
		request = DecisionRequest(policy=policy, state="text", modalities=frozenset({"text", "image"}))

		with self.assertRaises(DecisionError) as raised:
			prepare_state(
				request,
				policy,
				DecisionCapabilities(
					primitives=frozenset({QuestionKind.SELECT}),
					input_modalities=frozenset({"text"}),
				),
			)
		self.assertEqual(raised.exception.code, DecisionErrorCode.UNSUPPORTED_MODALITY)

	def test_image_and_audio_objects_are_rejected_when_declared_as_text(self):
		policy = _policy()
		multimodal_states = (
			{"content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]},
			{"content": [{"type": "input_audio", "input_audio": {"data": "AA==", "format": "wav"}}]},
		)

		for state in multimodal_states:
			with self.subTest(state=state):
				request = DecisionRequest(policy=policy, state=state, modalities=frozenset({"text"}))
				with self.assertRaises(DecisionError) as raised:
					prepare_state(
						request,
						policy,
						DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT})),
					)
				self.assertEqual(raised.exception.code, DecisionErrorCode.UNSUPPORTED_MODALITY)


if __name__ == "__main__":
	unittest.main()
