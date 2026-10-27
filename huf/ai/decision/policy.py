"""Validation and stable fingerprinting for data-only decision policies."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.types import DecisionPolicy, Option, Question, QuestionKind, StateBinding


def policy_fingerprint(policy: DecisionPolicy) -> str:
	"""Return a stable semantic fingerprint, excluding the fingerprint field itself."""
	payload = {
		"policy_id": policy.policy_id,
		"version": policy.version,
		"questions": [_question_data(question) for question in policy.questions],
		"minimum_confidence": policy.minimum_confidence,
		"fallback_action": policy.fallback_action,
		"store_state": policy.store_state,
		"max_state_bytes": policy.max_state_bytes,
		"required_modalities": sorted(policy.required_modalities),
		"state_bindings": [{"name": item.name, "path": item.path} for item in policy.state_bindings],
	}
	encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_policy(policy: DecisionPolicy) -> DecisionPolicy:
	"""Validate question shapes and return the policy with its computed fingerprint."""
	if not isinstance(policy, DecisionPolicy):
		raise DecisionError(DecisionErrorCode.POLICY_INVALID, "A normalized DecisionPolicy is required")
	for question in policy.questions:
		if not isinstance(question.kind, QuestionKind):
			raise DecisionError(DecisionErrorCode.POLICY_INVALID, f"Unsupported primitive for question {question.id}")
		if question.kind == QuestionKind.SELECT and len(question.options) < 2 and not question.allow_none:
			raise DecisionError(DecisionErrorCode.POLICY_INVALID, "select requires two options or allow_none")
		if question.kind == QuestionKind.JUDGE and not (question.positive_criteria or question.instructions.strip()):
			raise DecisionError(DecisionErrorCode.POLICY_INVALID, "judge requires precise criteria")
	return DecisionPolicy(
		policy_id=policy.policy_id,
		questions=policy.questions,
		fingerprint=policy_fingerprint(policy),
		version=policy.version,
		minimum_confidence=policy.minimum_confidence,
		fallback_action=policy.fallback_action,
		store_state=policy.store_state,
		max_state_bytes=policy.max_state_bytes,
		required_modalities=policy.required_modalities,
		state_bindings=policy.state_bindings,
	)


def validate_policy_data(data: Mapping[str, Any]) -> DecisionPolicy:
	"""Parse the supported policy JSON shape without evaluating executable content."""
	try:
		allowed_policy_keys = {
			"policy_id", "questions", "version", "minimum_confidence", "fallback_action",
			"store_state", "max_state_bytes", "required_modalities",
			"state_bindings",
		}
		if set(data) - allowed_policy_keys:
			raise ValueError("Unsupported policy fields")
		questions = tuple(_question_from_data(item) for item in data["questions"])
		policy = DecisionPolicy(
			policy_id=str(data["policy_id"]),
			questions=questions,
			version=data.get("version"),
			minimum_confidence=data.get("minimum_confidence"),
			fallback_action=data.get("fallback_action"),
			store_state=bool(data.get("store_state", False)),
			max_state_bytes=data.get("max_state_bytes"),
			required_modalities=frozenset(data.get("required_modalities", ["text"])),
			state_bindings=tuple(StateBinding(**item) for item in data.get("state_bindings", ())),
		)
		return validate_policy(policy)
	except (KeyError, TypeError, ValueError) as exc:
		raise DecisionError(DecisionErrorCode.POLICY_INVALID, "Policy definition is invalid") from exc


def _question_from_data(data: Mapping[str, Any]) -> Question:
	allowed_question_keys = {
		"id", "kind", "instructions", "options", "allow_none", "positive_criteria", "negative_criteria",
	}
	if set(data) - allowed_question_keys:
		raise ValueError("Unsupported question fields")
	return Question(
		id=str(data["id"]),
		kind=QuestionKind(data["kind"]),
		instructions=str(data["instructions"]),
		options=tuple(
			option if isinstance(option, Option) else Option(
				id=str(option["id"]), description=str(option.get("description", ""))
			)
			for option in data.get("options", ())
		),
		allow_none=bool(data.get("allow_none", False)),
		positive_criteria=str(data.get("positive_criteria", "")),
		negative_criteria=str(data.get("negative_criteria", "")),
	)


def _question_data(question: Question) -> dict[str, Any]:
	return {
		"id": question.id,
		"kind": question.kind.value,
		"instructions": question.instructions,
		"options": [{"id": item.id, "description": item.description} for item in question.options],
		"allow_none": question.allow_none,
		"positive_criteria": question.positive_criteria,
		"negative_criteria": question.negative_criteria,
	}
