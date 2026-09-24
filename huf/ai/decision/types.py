"""Immutable, provider-neutral value objects for Decision Runtime calls."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class QuestionKind(str, Enum):
	SELECT = "select"
	JUDGE = "judge"
	SCORE = "score"


class DecisionStatus(str, Enum):
	SUCCESS = "success"
	UNSUPPORTED = "unsupported"
	UNAVAILABLE = "unavailable"
	AUTHENTICATION_FAILED = "authentication_failed"
	INVALID_RESPONSE = "invalid_response"
	TIMEOUT = "timeout"
	RATE_LIMITED = "rate_limited"
	THROUGHPUT_BUDGET_EXHAUSTED = "throughput_budget_exhausted"
	FAILED = "failed"


class CandidateSource(str, Enum):
	"""Declared origin of candidates after deterministic hard filters."""

	POLICY_OPTIONS = "policy_options"
	ROUTEABLE_MODELS = "routeable_models"
	PERMISSION_FILTERED_TOOLS = "permission_filtered_tools"
	BOUND_ALLOWED_PROCEDURES = "bound_allowed_procedures"
	AUTHORIZED_AGENTS = "authorized_agents"
	PERMITTED_SKILLS = "permitted_skills"
	AUTHORIZED_KNOWLEDGE_CHUNKS = "authorized_knowledge_chunks"
	MODEL_SUPPLIED_CANDIDATES = "model_supplied_candidates"
	# T8.04 (Context Relevance, PLAN.md §3.6): completed old tool exchanges from conversation
	# history, already filtered by huf.ai.conversation_manager.get_tool_exchange_candidates /
	# huf.ai.decision.context_relevance.compact_context to exclude anything recent, errored, or
	# tied to a pending approval (I-DR1) before they are ever offered as candidates.
	COMPLETED_TOOL_EXCHANGES = "completed_tool_exchanges"


@dataclass(frozen=True, slots=True)
class Option:
	"""A caller-supplied, closed candidate or rubric level."""

	id: str
	description: str = ""

	def __post_init__(self) -> None:
		if not self.id or not self.id.strip():
			raise ValueError("Option id is required")
		if len(self.id) > 128:
			raise ValueError("Option id must be at most 128 characters")


@dataclass(frozen=True, slots=True)
class Question:
	"""One normalized select, judge, or score question."""

	id: str
	kind: QuestionKind
	instructions: str
	options: tuple[Option, ...] = ()
	allow_none: bool = False
	positive_criteria: str = ""
	negative_criteria: str = ""

	def __post_init__(self) -> None:
		if not self.id or not self.id.strip():
			raise ValueError("Question id is required")
		if not self.instructions or not self.instructions.strip():
			raise ValueError("Question instructions are required")
		if self.kind in (QuestionKind.SELECT, QuestionKind.SCORE) and not self.options:
			raise ValueError(f"{self.kind.value} requires options")
		ids = [option.id for option in self.options]
		if len(ids) != len(set(ids)):
			raise ValueError("Question option ids must be unique")


@dataclass(frozen=True, slots=True)
class DecisionCapabilities:
	"""Honest backend limits and supported normalized features."""

	primitives: frozenset[QuestionKind]
	parallel_questions: bool = True
	probabilities: bool = False
	confidence: bool = False
	input_modalities: frozenset[str] = frozenset({"text"})
	max_state_bytes: int | None = None
	max_candidates_per_select: int | None = None

	def __post_init__(self) -> None:
		if self.max_state_bytes is not None and self.max_state_bytes <= 0:
			raise ValueError("max_state_bytes must be positive")
		if self.max_candidates_per_select is not None and self.max_candidates_per_select <= 0:
			raise ValueError("max_candidates_per_select must be positive")


@dataclass(frozen=True, slots=True)
class DecisionUsage:
	"""Usage values preserve unknown as None rather than inventing zero."""

	input_tokens: int | None = None
	output_tokens: int | None = None
	measured_cost: float | None = None
	cost_source: str | None = None

	def __post_init__(self) -> None:
		for field_name in ("input_tokens", "output_tokens"):
			value = getattr(self, field_name)
			if value is not None and value < 0:
				raise ValueError(f"{field_name} cannot be negative")
		if self.measured_cost is not None and (not math.isfinite(self.measured_cost) or self.measured_cost < 0):
			raise ValueError("measured_cost must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class DecisionIdentity:
	"""Canonical model identity and serving deployment kept as separate fields."""

	model_class: str | None = None
	model_family: str | None = None
	canonical_model: str | None = None
	canonical_version: str | None = None
	provider: str | None = None
	deployment: str | None = None
	provider_model_id: str | None = None


@dataclass(frozen=True, slots=True)
class StateBinding:
	"""Explicit provider-visible state field projected from request state."""

	name: str
	path: str

	def __post_init__(self) -> None:
		if not self.name.strip() or not self.path.strip():
			raise ValueError("State binding name and path are required")


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
	"""Bounded, data-only policy definition; no executable expressions."""

	policy_id: str
	questions: tuple[Question, ...]
	fingerprint: str = ""
	version: str | None = None
	minimum_confidence: float | None = None
	fallback_action: str | None = None
	store_state: bool = False
	max_state_bytes: int | None = None
	required_modalities: frozenset[str] = frozenset({"text"})
	state_bindings: tuple[StateBinding, ...] = ()

	def __post_init__(self) -> None:
		if not self.policy_id.strip():
			raise ValueError("policy_id is required")
		if not self.questions:
			raise ValueError("Policy must define at least one question")
		ids = [question.id for question in self.questions]
		if len(ids) != len(set(ids)):
			raise ValueError("Policy question ids must be unique")
		if self.minimum_confidence is not None and not 0 <= self.minimum_confidence <= 1:
			raise ValueError("minimum_confidence must be between 0 and 1")
		if self.max_state_bytes is not None and self.max_state_bytes <= 0:
			raise ValueError("max_state_bytes must be positive")
		binding_names = [binding.name for binding in self.state_bindings]
		if len(binding_names) != len(set(binding_names)):
			raise ValueError("State binding names must be unique")


@dataclass(frozen=True, slots=True)
class DecisionRequest:
	"""One provider-visible state and a batch of questions about that state."""

	policy: DecisionPolicy
	state: Any
	identity: DecisionIdentity = field(default_factory=DecisionIdentity)
	surface: str = "generic"
	candidates: tuple[Option, ...] = ()
	candidate_source: CandidateSource | None = None
	candidate_resolver_id: str | None = None
	modalities: frozenset[str] = frozenset({"text"})
	execution_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionBackendRequest:
	"""Sanitized backend input; deliberately excludes HUF execution context."""

	policy: DecisionPolicy
	state: Any
	identity: DecisionIdentity
	surface: str
	candidates: tuple[Option, ...]
	candidate_source: CandidateSource | None
	candidate_resolver_id: str | None
	modalities: frozenset[str]


@dataclass(frozen=True, slots=True)
class DecisionAnswer:
	"""Normalized answer; backend metadata is diagnostic only."""

	question_id: str
	kind: QuestionKind
	value: str | float
	probabilities: Mapping[str, float] | None = None
	confidence: float | None = None
	backend_metadata: Mapping[str, Any] = field(default_factory=dict)

	def __post_init__(self) -> None:
		if not self.question_id.strip():
			raise ValueError("question_id is required")
		if self.kind == QuestionKind.JUDGE and (not isinstance(self.value, (int, float)) or not 0 <= self.value <= 1):
			raise ValueError("judge value must be a probability in [0, 1]")
		if self.confidence is not None and not 0 <= self.confidence <= 1:
			raise ValueError("confidence must be in [0, 1]")
		if self.probabilities is not None:
			if any(not 0 <= value <= 1 for value in self.probabilities.values()):
				raise ValueError("probabilities must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class DecisionResponse:
	"""Caller-facing normalized result with separate execution metadata."""

	status: DecisionStatus
	answers: Mapping[str, DecisionAnswer] = field(default_factory=dict)
	identity: DecisionIdentity = field(default_factory=DecisionIdentity)
	backend_adapter: str | None = None
	requested_identity: DecisionIdentity = field(default_factory=DecisionIdentity)
	requested_model: str | None = None
	requested_model_version: str | None = None
	resolved_model: str | None = None
	resolved_model_version: str | None = None
	usage: DecisionUsage = field(default_factory=DecisionUsage)
	latency_ms: float | None = None
	error_code: str | None = None
	policy_fallback_action: str | None = None
	gate_result: str | None = None
	deployment_selection_source: str | None = None
	deployment_fallback_count: int = 0
	deployment_fallback_chain: tuple[str, ...] = ()

	def __post_init__(self) -> None:
		if self.latency_ms is not None and self.latency_ms < 0:
			raise ValueError("latency_ms cannot be negative")
		if self.deployment_fallback_count < 0:
			raise ValueError("deployment_fallback_count cannot be negative")


@dataclass(frozen=True, slots=True)
class DeploymentSpec:
	"""Deployment identity, capabilities, and configuration for backend instantiation."""

	identity: DecisionIdentity
	effective_capabilities: DecisionCapabilities
	wire_protocol: str
	endpoint_path: str | None = None
	latency_budget_ms: int | None = None

	def __post_init__(self) -> None:
		if self.latency_budget_ms is not None and self.latency_budget_ms <= 0:
			raise ValueError("latency_budget_ms must be positive")
		if not self.wire_protocol or not self.wire_protocol.strip():
			raise ValueError("wire_protocol is required")


@dataclass(frozen=True, slots=True)
class DecisionOrigin:
	"""Origin of a decision call for linking to its source execution context."""

	origin_type: str
	agent: str | None = None
	agent_run: str | None = None
	conversation: str | None = None
	flow_run: str | None = None
	flow_node_id: str | None = None
	automation: str | None = None
	owner_user: str | None = None
	shadow_of: str | None = None

	def __post_init__(self) -> None:
		if not self.origin_type or not self.origin_type.strip():
			raise ValueError("origin_type is required")


@dataclass(frozen=True, slots=True)
class ServiceResult:
	"""Result of a decision service call with status and resolved resources."""

	status: DecisionStatus
	response: DecisionResponse | None = None
	decision_call: str | None = None
	fallback_action: str | None = None
