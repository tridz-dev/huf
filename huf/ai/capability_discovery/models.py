"""Capability descriptor models and builders for HUF app capability discovery."""

CAPABILITY_KINDS = ("resource", "action", "event", "schedule", "workflow", "report")
SOURCE_TYPES = ("declared", "framework_discovered", "generated", "inferred")
MUTATION_LEVELS = ("read", "write", "destructive", "unknown")
VISIBILITY_LEVELS = ("recommended", "normal", "advanced", "hidden")
ACTIONABILITY_LEVELS = ("actionable_now", "informational", "requires_adapter", "requires_app_declaration")


def build_capability_id(kind: str, source_app: str, source_key: str) -> str:
    """Build a stable capability identifier."""
    return f"{kind}:{source_app}:{source_key}"


def make_capability_descriptor(
    *,
    kind,
    source_app,
    source_type,
    source_key,
    title,
    short_description=None,
    description=None,
    category=None,
    resource_doctype=None,
    function_path=None,
    event_name=None,
    hook_name=None,
    parameters_schema=None,
    payload_schema=None,
    return_schema=None,
    read_only=None,
    mutation_level="unknown",
    required_permission=None,
    allow_guest=False,
    confidence=1.0,
    relevance_score=0.0,
    visibility="normal",
    actionability="actionable_now",
    metadata=None,
) -> dict:
    """Validate and build a capability descriptor dictionary.

    Raises ValueError if kind, source_type, mutation_level, visibility, or actionability
    are not in their respective allowed values.
    """
    if kind not in CAPABILITY_KINDS:
        raise ValueError(f"kind must be one of {CAPABILITY_KINDS}, got {kind!r}")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {SOURCE_TYPES}, got {source_type!r}")
    if mutation_level not in MUTATION_LEVELS:
        raise ValueError(f"mutation_level must be one of {MUTATION_LEVELS}, got {mutation_level!r}")
    if visibility not in VISIBILITY_LEVELS:
        raise ValueError(f"visibility must be one of {VISIBILITY_LEVELS}, got {visibility!r}")
    if actionability not in ACTIONABILITY_LEVELS:
        raise ValueError(f"actionability must be one of {ACTIONABILITY_LEVELS}, got {actionability!r}")

    capability_id = build_capability_id(kind, source_app, source_key)

    return {
        "id": capability_id,
        "kind": kind,
        "source_app": source_app,
        "source_type": source_type,
        "source_key": source_key,
        "title": title,
        "short_description": short_description,
        "description": description,
        "category": category,
        "resource_doctype": resource_doctype,
        "function_path": function_path,
        "event_name": event_name,
        "hook_name": hook_name,
        "parameters_schema": parameters_schema if parameters_schema is not None or kind != "action" else [],
        "payload_schema": payload_schema,
        "return_schema": return_schema,
        "read_only": read_only,
        "mutation_level": mutation_level,
        "required_permission": required_permission,
        "allow_guest": allow_guest,
        "confidence": confidence,
        "relevance_score": relevance_score,
        "visibility": visibility,
        "actionability": actionability,
        "metadata": metadata if metadata is not None else {},
    }
