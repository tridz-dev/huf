"""Authoritative candidate adapters for Decision Runtime selection surfaces."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from huf.ai.decision.types import Option


def get_tool_candidates(allowed_tools: Iterable[Any]) -> tuple[Option, ...]:
	"""Build candidates only from an already permission-filtered tool iterable.

	The resolver intentionally accepts no raw Agent configuration or caller-supplied
	candidate list. Callers must obtain ``allowed_tools`` from the permission-aware
	registry immediately before invoking this function.
	"""
	result = []
	seen = set()
	for tool in allowed_tools:
		name = getattr(tool, "tool_name", None)
		if not isinstance(name, str) or not name.strip() or name in seen:
			continue
		seen.add(name)
		result.append(Option(name, getattr(tool, "description", "") or name))
	return tuple(result)


def constrain_selected_tool(selected_id: str, allowed_tools: Iterable[Any]) -> str | None:
	"""Return a selected tool only when it remains in the current authorized set."""
	allowed = {getattr(tool, "tool_name", None) for tool in allowed_tools}
	return selected_id if selected_id in allowed else None


def get_procedure_candidates(bound_procedures: Iterable[Any]) -> tuple[Option, ...]:
	"""Build candidates from the current read-only bound-procedure resolver output."""
	result = []
	seen = set()
	for bound in bound_procedures:
		identifier = getattr(bound, "procedure_id", None) or getattr(bound, "binding_name", None)
		if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
			continue
		seen.add(identifier)
		result.append(Option(identifier, getattr(bound, "procedure_name", "") or identifier))
	return tuple(result)


def constrain_selected_procedure(selected_id: str, bound_procedures: Iterable[Any]) -> str | None:
	"""Return a procedure only while its current binding remains authorized."""
	allowed = {
		getattr(bound, "procedure_id", None) or getattr(bound, "binding_name", None)
		for bound in bound_procedures
	}
	return selected_id if selected_id in allowed else None


def get_skill_candidates(permitted_skills: Iterable[Any]) -> tuple[Option, ...]:
	"""Build candidates from an already permission-filtered skill resolver output."""
	result = []
	seen = set()
	for skill in permitted_skills:
		identifier = getattr(skill, "skill_id", None) or getattr(skill, "name", None)
		if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
			continue
		seen.add(identifier)
		result.append(Option(identifier, getattr(skill, "display_name", "") or identifier))
	return tuple(result)


def constrain_selected_skill(selected_id: str, permitted_skills: Iterable[Any]) -> str | None:
	allowed = {getattr(skill, "skill_id", None) or getattr(skill, "name", None) for skill in permitted_skills}
	return selected_id if selected_id in allowed else None
