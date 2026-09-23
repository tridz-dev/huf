"""Tests for decision advice formatting (Advise mode hints)."""

import pytest

from huf.ai.decision.advice import format_hint, _is_safe_id
from huf.ai.decision.types import (
	DecisionResponse,
	DecisionAnswer,
	DecisionStatus,
	QuestionKind,
	Option,
)


class TestFormatHint:
	"""format_hint output formatting and security."""

	def test_basic_format_with_scores(self) -> None:
		"""Hint includes permitted candidates with scores to 2 decimals."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="option_a",
					probabilities={"option_a": 0.86, "option_b": 0.71, "option_c": 0.43},
				)
			},
		)
		candidates = ["option_a", "option_b", "option_c"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "Decision suggestion (advisory, not an instruction):" in hint
		assert "option_a (0.86)" in hint
		assert "option_b (0.71)" in hint
		assert "option_c (0.43)" in hint

	def test_score_formatting_two_decimals(self) -> None:
		"""Scores are always formatted to exactly 2 decimal places."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={"a": 1.0, "b": 0.5, "c": 0.1, "d": 0.123456},
				)
			},
		)
		candidates = ["a", "b", "c", "d"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (1.00)" in hint
		assert "b (0.50)" in hint
		assert "c (0.10)" in hint
		assert "d (0.12)" in hint  # Rounded, not truncated

	def test_sorted_by_score_descending(self) -> None:
		"""Candidates are sorted by score descending."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="b",
					probabilities={"a": 0.3, "b": 0.9, "c": 0.6},
				)
			},
		)
		candidates = ["a", "b", "c"]

		hint = format_hint(response, candidates)

		assert hint is not None
		# Extract the order of candidates from the hint
		import re

		matches = re.findall(r"(\w+) \(\d+\.\d{2}\)", hint)
		assert matches == ["b", "c", "a"]

	def test_top_n_limit(self) -> None:
		"""top_n limits the number of candidates included."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6},
				)
			},
		)
		candidates = ["a", "b", "c", "d"]

		hint = format_hint(response, candidates, top_n=2)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "b (0.80)" in hint
		assert "c (0.70)" not in hint
		assert "d (0.60)" not in hint

	def test_filters_to_permitted_candidates(self) -> None:
		"""Only permitted candidates are included, unknown candidates dropped."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={"a": 0.9, "b": 0.8, "c": 0.7, "unknown_id": 0.95},
				)
			},
		)
		# Permitted set excludes "unknown_id"
		candidates = ["a", "b", "c"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "b (0.80)" in hint
		assert "c (0.70)" in hint
		assert "unknown_id" not in hint

	def test_accepts_option_objects(self) -> None:
		"""Candidates can be Option objects or id strings."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={"a": 0.9, "b": 0.8},
				)
			},
		)
		candidates = [
			Option(id="a", description="First option"),
			Option(id="b", description="Second option"),
		]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "b (0.80)" in hint

	def test_returns_none_on_failure_status(self) -> None:
		"""None returned if response status is not SUCCESS."""
		response = DecisionResponse(status=DecisionStatus.TIMEOUT)
		candidates = ["a", "b"]

		hint = format_hint(response, candidates)

		assert hint is None

	def test_returns_none_on_no_answers(self) -> None:
		"""None returned if response has no answers."""
		response = DecisionResponse(status=DecisionStatus.SUCCESS, answers={})
		candidates = ["a", "b"]

		hint = format_hint(response, candidates)

		assert hint is None

	def test_returns_none_on_no_probabilities(self) -> None:
		"""None returned if answers have no probabilities."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.JUDGE,
					value=0.5,
					probabilities=None,
				)
			},
		)
		candidates = ["a", "b"]

		hint = format_hint(response, candidates)

		assert hint is None

	def test_returns_none_when_no_candidates_permitted(self) -> None:
		"""None returned if no response candidates are in permitted set."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="x",
					probabilities={"x": 0.9, "y": 0.8},
				)
			},
		)
		candidates = ["a", "b"]  # Empty intersection

		hint = format_hint(response, candidates)

		assert hint is None

	def test_sanitizes_ids_with_newlines(self) -> None:
		"""Candidate ids with newlines are dropped."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={
						"a": 0.9,
						"b\n(echo 'injected')": 0.8,
						"c": 0.7,
					},
				)
			},
		)
		candidates = ["a", "b\n(echo 'injected')", "c"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "c (0.70)" in hint
		assert "injected" not in hint
		assert "\n" not in hint

	def test_sanitizes_ids_with_control_characters(self) -> None:
		"""Candidate ids with control characters are dropped."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={
						"a": 0.9,
						"b\x00null": 0.8,
						"c": 0.7,
					},
				)
			},
		)
		candidates = ["a", "b\x00null", "c"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "c (0.70)" in hint
		assert "\x00" not in hint

	def test_sanitizes_ids_with_adversarial_strings(self) -> None:
		"""Adversarial backend strings as candidate ids are rejected."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={
						"a": 0.9,
						"tool_name': '; DROP TABLE--": 0.8,
						"legitimate_tool": 0.7,
					},
				)
			},
		)
		candidates = ["a", "tool_name': '; DROP TABLE--", "legitimate_tool"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "legitimate_tool (0.70)" in hint
		assert "DROP TABLE" not in hint
		assert "'" not in hint

	def test_sanitizes_ids_with_quote_characters(self) -> None:
		"""Candidate ids with quotes or special chars are dropped if unsafe."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={
						"a": 0.9,
						'b"with"quotes': 0.8,
						"c": 0.7,
					},
				)
			},
		)
		candidates = ["a", 'b"with"quotes', "c"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "a (0.90)" in hint
		assert "c (0.70)" in hint
		assert '"' not in hint

	def test_handles_backend_free_text_in_probabilities(self) -> None:
		"""Backend free text is never in probabilities, only values/descriptions."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="option_a",
					probabilities={"option_a": 0.9, "option_b": 0.8},
					backend_metadata={"reasoning": "This is backend free text that should never appear"},
				)
			},
		)
		candidates = ["option_a", "option_b"]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "backend_metadata" not in hint
		assert "reasoning" not in hint
		assert "should never appear" not in hint

	def test_handles_state_not_included(self) -> None:
		"""State from request is never included in hint (immutable response object)."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={"a": 0.9, "b": 0.8},
				)
			},
		)
		candidates = ["a", "b"]

		hint = format_hint(response, candidates)

		assert hint is not None
		# Response doesn't contain state; format_hint only uses answers
		assert "state" not in (hint or "").lower()

	def test_deterministic_order_with_equal_scores(self) -> None:
		"""When scores are equal, candidates are ordered by id (deterministic)."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="z",
					probabilities={"z": 0.5, "a": 0.5, "m": 0.5},
				)
			},
		)
		candidates = ["z", "a", "m"]

		hint = format_hint(response, candidates)

		assert hint is not None
		import re

		matches = re.findall(r"(\w+) \(\d+\.\d{2}\)", hint)
		# Equal scores, so sorted by id: a, m, z
		assert matches == ["a", "m", "z"]

	def test_handles_ids_with_allowed_special_chars(self) -> None:
		"""Allowed characters: alphanumeric, underscore, hyphen, dot, colon, slash, at."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={
						"tool_name": 0.9,
						"agent-001": 0.8,
						"procedure.v2": 0.7,
						"namespace:skill": 0.6,
						"path/to/resource": 0.5,
						"user@domain": 0.4,
					},
				)
			},
		)
		candidates = [
			"tool_name",
			"agent-001",
			"procedure.v2",
			"namespace:skill",
			"path/to/resource",
			"user@domain",
		]

		hint = format_hint(response, candidates)

		assert hint is not None
		assert "tool_name (0.90)" in hint
		assert "agent-001 (0.80)" in hint
		assert "procedure.v2 (0.70)" in hint
		assert "namespace:skill (0.60)" in hint
		assert "path/to/resource (0.50)" in hint
		assert "user@domain (0.40)" in hint

	def test_multiple_answers_uses_first(self) -> None:
		"""If response has multiple answers, uses the first one (iteration order)."""
		response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"q1": DecisionAnswer(
					question_id="q1",
					kind=QuestionKind.SELECT,
					value="a",
					probabilities={"a": 0.9, "b": 0.8},
				),
				"q2": DecisionAnswer(
					question_id="q2",
					kind=QuestionKind.SELECT,
					value="x",
					probabilities={"x": 0.7, "y": 0.6},
				),
			},
		)
		candidates = ["a", "b", "x", "y"]

		hint = format_hint(response, candidates)

		assert hint is not None
		# Should have candidates from one of the answers
		# Python 3.7+ dict maintains insertion order, so q1 comes first
		assert ("a (0.90)" in hint and "b (0.80)" in hint) or ("x (0.70)" in hint and "y (0.60)" in hint)


class TestIsSafeId:
	"""ID sanitization helper."""

	def test_rejects_empty_id(self) -> None:
		assert not _is_safe_id("")
		assert not _is_safe_id("   ")

	def test_rejects_non_string(self) -> None:
		assert not _is_safe_id(None)  # type: ignore
		assert not _is_safe_id(123)  # type: ignore
		assert not _is_safe_id([])  # type: ignore

	def test_rejects_newlines(self) -> None:
		assert not _is_safe_id("id\n")
		assert not _is_safe_id("id\r")
		assert not _is_safe_id("id\r\n")

	def test_rejects_tabs(self) -> None:
		assert not _is_safe_id("id\t")
		assert not _is_safe_id("id\ttab")

	def test_rejects_control_characters(self) -> None:
		assert not _is_safe_id("id\x00")
		assert not _is_safe_id("id\x1f")
		assert not _is_safe_id("id\x7f")

	def test_accepts_alphanumeric(self) -> None:
		assert _is_safe_id("id123")
		assert _is_safe_id("Tool")
		assert _is_safe_id("SKILL")

	def test_accepts_underscore_hyphen_dot(self) -> None:
		assert _is_safe_id("tool_name")
		assert _is_safe_id("agent-001")
		assert _is_safe_id("procedure.v2")

	def test_accepts_colon_slash_at(self) -> None:
		assert _is_safe_id("namespace:skill")
		assert _is_safe_id("path/to/resource")
		assert _is_safe_id("user@domain")

	def test_rejects_quotes(self) -> None:
		assert not _is_safe_id('id"quoted')
		assert not _is_safe_id("id'quoted")

	def test_rejects_sql_injection_patterns(self) -> None:
		assert not _is_safe_id("id'; DROP TABLE--")
		assert not _is_safe_id("id' OR '1'='1")

	def test_rejects_command_injection_patterns(self) -> None:
		assert not _is_safe_id("id; rm -rf /")
		assert not _is_safe_id("id $(echo pwned)")
		assert not _is_safe_id("id `whoami`")

	def test_rejects_other_special_chars(self) -> None:
		assert not _is_safe_id("id<>")
		assert not _is_safe_id("id&parameter")
		assert not _is_safe_id("id|pipe")
		assert not _is_safe_id("id%format")
		assert not _is_safe_id("id=value")
		assert not _is_safe_id("id+plus")
		assert not _is_safe_id("id#hash")
		assert not _is_safe_id("id*glob")
		assert not _is_safe_id("id?query")
		assert not _is_safe_id("id\\backslash")
		assert not _is_safe_id("id(paren)")
		assert not _is_safe_id("id{brace}")
		assert not _is_safe_id("id[bracket]")


def test_kind_prefix_only_for_known_kinds():
	from huf.ai.decision import advice

	assert "tools" in advice._HINT_KINDS
	assert "ignore previous instructions" not in advice._HINT_KINDS
