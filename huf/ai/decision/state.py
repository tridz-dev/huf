"""Provider-visible state normalization, modality checks, and size limits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.types import DecisionCapabilities, DecisionPolicy, DecisionRequest


@dataclass(frozen=True, slots=True)
class PreparedState:
	value: Any
	canonical_json: str
	sha256: str
	size_bytes: int


def prepare_state(
	request: DecisionRequest,
	policy: DecisionPolicy,
	capabilities: DecisionCapabilities,
) -> PreparedState:
	"""Serialize bounded state and reject unsupported modalities before dispatch."""
	detected_modalities = _detect_modalities(request.state)
	effective_modalities = request.modalities | detected_modalities
	if not detected_modalities <= request.modalities:
		raise DecisionError(DecisionErrorCode.UNSUPPORTED_MODALITY)
	if not effective_modalities <= capabilities.input_modalities:
		raise DecisionError(DecisionErrorCode.UNSUPPORTED_MODALITY)
	if not policy.required_modalities <= effective_modalities:
		raise DecisionError(DecisionErrorCode.UNSUPPORTED_MODALITY)
	if not policy.state_bindings:
		raise DecisionError(DecisionErrorCode.POLICY_INVALID, "Policy must explicitly bind provider-visible state")
	projected_state = _project_state(request.state, policy)
	try:
		canonical = json.dumps(
			projected_state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
		)
	except (TypeError, ValueError) as exc:
		raise DecisionError(DecisionErrorCode.POLICY_INVALID, "Decision state must be JSON-serializable") from exc
	encoded = canonical.encode("utf-8")
	limits = [limit for limit in (policy.max_state_bytes, capabilities.max_state_bytes) if limit is not None]
	if limits and len(encoded) > min(limits):
		raise DecisionError(DecisionErrorCode.STATE_TOO_LARGE)
	import hashlib

	return PreparedState(json.loads(canonical), canonical, hashlib.sha256(encoded).hexdigest(), len(encoded))


def _project_state(state: Any, policy: DecisionPolicy) -> dict[str, Any]:
	projected: dict[str, Any] = {}
	for binding in policy.state_bindings:
		if binding.path == "$":
			value = state
		else:
			value = state
			for part in binding.path.split("."):
				if isinstance(value, dict) and part in value:
					value = value[part]
				elif isinstance(value, (list, tuple)) and part.isdigit() and int(part) < len(value):
					value = value[int(part)]
				else:
					raise DecisionError(DecisionErrorCode.POLICY_INVALID, "A required state binding is missing")
		projected[binding.name] = value
	return projected


def _detect_modalities(value: Any, key: str = "") -> frozenset[str]:
	"""Detect common structured media payloads even when callers mislabel modality."""
	if isinstance(value, (bytes, bytearray, memoryview)):
		return frozenset({"binary"})
	modalities: set[str] = set()
	key_lower = key.lower()
	if key_lower in {
		"image", "images", "image_url", "image_data", "audio", "audio_url", "audio_data", "input_audio",
		"video", "video_url", "video_data", "frames",
	}:
		if key_lower.startswith("image"):
			modalities.add("image")
		elif key_lower.startswith("audio"):
			modalities.add("audio")
		else:
			modalities.add("video")
	if isinstance(value, str) and value.lower().startswith(("data:image/", "data:audio/", "data:video/")):
		media_type = value[5:].split("/", 1)[0].lower()
		modalities.add(media_type)
	if isinstance(value, dict):
		mime_type = value.get("mime_type") or value.get("mimeType")
		if isinstance(mime_type, str):
			media_type = mime_type.split("/", 1)[0].lower()
			if media_type in {"image", "audio", "video"}:
				modalities.add(media_type)
		for child_key, child in value.items():
			modalities.update(_detect_modalities(child, str(child_key)))
	elif isinstance(value, (list, tuple)):
		for child in value:
			modalities.update(_detect_modalities(child, key))
	return frozenset(modalities)
