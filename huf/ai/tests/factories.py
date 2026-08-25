# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Factory/bootstrap helpers for constructing a deterministic Frappe world in
real-Frappe integration tests (Layer B, run under `bench run-tests`).

Concept salvaged from historical PR #359's `HufTestSuite` +
`BootStrapTestData` (mirroring `ERPNextTestSuite`/`HRMSTestSuite`) — see
`docs/testing/PR359_SALVAGE.md` ("HufTestSuite + BootStrapTestData shared
fixture base class", classified STALE-CONCEPT: the *idea* survives, the old
code does not, because it was written against an earlier DocType shape).
This module is a from-scratch rewrite against current `develop`'s actual
schema, verified field-by-field against the real doctype JSON (citations in
each function's docstring) rather than guessed.

Project rule this module exists to serve (see `docs/testing/CURRENT_STATE.md`):
tests must build their own deterministic world and assert real behavior,
never `if no model: skipTest(...)` away essential regression coverage.
Every factory here is safe to call with zero pre-existing fixtures on a
freshly migrated site — it creates whatever it needs (Provider before Model,
etc.) rather than assuming seed data exists.

Usage (real bench, `IntegrationTestCase` style — see
`huf/huf/doctype/agent/test_agent.py` for the established repo convention of
ad-hoc `setUp`/`tearDown` cleanup rather than a shared base-class fixture
loader):

    from huf.ai.tests.factories import make_agent, make_ai_provider_and_model

    class TestSomething(IntegrationTestCase):
        def setUp(self):
            self.provider, self.model = make_ai_provider_and_model()
            self.agent = make_agent(provider=self.provider, model=self.model)

        def tearDown(self):
            frappe.db.delete("Agent", {"name": self.agent.name})
            frappe.db.delete("AI Model", {"name": self.model})
            frappe.db.delete("AI Provider", {"name": self.provider})
            frappe.db.commit()

Every factory function:
  - accepts keyword-argument overrides for the fields a test is likely to
    care about,
  - fills in every doctype-required field with a safe, unique-enough default
    (via `frappe.generate_hash`) so `.insert()` never fails on a missing
    required field,
  - inserts with `ignore_permissions=True` (matching the repo's existing
    test convention — see `test_agent.py`'s `insert(ignore_permissions=True)`
    calls throughout) and returns the inserted `Document`,
  - does NOT attempt cleanup — callers own their own `tearDown`/`frappe.db.delete`,
    exactly as every existing test file in this repo does today (there is no
    shared teardown registry to hook into).

No bench is available in this environment to execute these against a real
DB. Field names/required-ness below were verified by reading the actual
doctype JSON files, not guessed — see each function's docstring for the
file:line-equivalent citation (JSON files have no stable line numbers across
edits, so citations reference field names within the file instead).
"""

import frappe


def _hash(n=8):
    return frappe.generate_hash(length=n)


# ---------------------------------------------------------------------------
# User / Role
# ---------------------------------------------------------------------------


def make_role(role_name=None, **overrides):
    """Create a standard Frappe ``Role`` (not a Huf-specific doctype).

    Required field per Frappe core ``role.json``: ``role_name`` (Data, reqd=1).
    Mirrors the existing repo convention of appending role rows to a User's
    child table (see `huf/ai/tests/test_ssh_execution.py:133`,
    `user.append("roles", {"role": role})`) — this factory is for cases where
    a *custom* role needs to exist first (e.g. testing a not-yet-seeded Huf
    role), not for the built-in "Huf User"/"System Manager" roles that
    `huf.install.create_huf_roles()` already seeds.
    """
    fields = {
        "doctype": "Role",
        "role_name": role_name or f"Test Role {_hash()}",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_user(email=None, roles=("Huf User",), first_name="Test", **overrides):
    """Create a standard Frappe ``User`` with role assignment.

    Required fields per Frappe core ``user.json``: ``email`` (also the
    document's ``name``). ``send_welcome_email`` defaulted to 0 to avoid
    outbound-email side effects in tests (matching
    `huf/huf/doctype/agent/test_agent.py:404-412`'s `_make_user` helper).

    Roles are appended to the ``roles`` child table (fieldname ``role``,
    linking to Role) — the exact pattern already used at
    `test_agent.py:410-411` / `test_ssh_execution.py:133`.
    """
    fields = {
        "doctype": "User",
        "email": email or f"huf-factory-test-{_hash(10)}@example.com",
        "first_name": first_name,
        "send_welcome_email": 0,
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    for role in roles or ():
        doc.append("roles", {"role": role})
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# AI Provider / AI Model
# ---------------------------------------------------------------------------


def make_ai_provider(provider_name=None, provider_brand="openai", **overrides):
    """Create an ``AI Provider``.

    Required fields per `huf/huf/doctype/ai_provider/ai_provider.json`:
    ``provider_name`` (Data, reqd=1), ``provider_brand`` (Select, reqd=1;
    options include openai/anthropic/google/... /other). ``api_key`` is a
    Password field (not required by the doctype itself) — a harmless
    placeholder is set so any code path that reads it doesn't choke on None,
    mirroring `test_agent.py:378` (`_ensure_provider`)'s
    ``"api_key": "test-key-not-used"``.
    """
    fields = {
        "doctype": "AI Provider",
        # Single word: AIProvider.validate_provider_name() rejects whitespace
        # on insert (the name becomes the LiteLLM model routing prefix).
        "provider_name": provider_name or f"TestProvider{_hash()}",
        "provider_brand": provider_brand,
        "api_key": "test-key-not-used",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_ai_model(provider=None, model_name=None, **overrides):
    """Create an ``AI Model`` linked to an ``AI Provider``.

    Required fields per `huf/huf/doctype/ai_model/ai_model.json`:
    ``provider`` (Link -> AI Provider, reqd=1), ``model_name`` (Data, reqd=1).
    If ``provider`` is not supplied, one is created via `make_ai_provider()`
    so this factory is self-sufficient on a bare site (no seed data needed).

    Note the controller's `validate()` (`huf/huf/doctype/ai_model/ai_model.py`)
    additionally requires both `input_cost_per_1m_tokens` and
    `output_cost_per_1m_tokens` to be set together if `use_custom_pricing` is
    truthy — this factory leaves `use_custom_pricing` unset/falsy by default
    to avoid that extra requirement, matching the minimal-valid-doc spirit of
    every other factory here.
    """
    if provider is None:
        provider = make_ai_provider().name

    fields = {
        "doctype": "AI Model",
        "provider": provider,
        "model_name": model_name or f"test-model-{_hash()}",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_ai_provider_and_model(provider_kwargs=None, model_kwargs=None):
    """Convenience: create a linked (AI Provider, AI Model) pair.

    Returns (provider_name, model_name) — the two string names most Agent
    factories below actually need, matching the `(model, provider)` tuple
    shape `huf/huf/doctype/agent/test_agent.py:21-25`'s `_any_model_and_provider()`
    already returns elsewhere in this repo.
    """
    provider = make_ai_provider(**(provider_kwargs or {}))
    model = make_ai_model(provider=provider.name, **(model_kwargs or {}))
    return provider.name, model.name


# ---------------------------------------------------------------------------
# Agent Prompt (the actual "prompt template" doctype — see prompt_resolver.py)
# ---------------------------------------------------------------------------


def make_agent_prompt(title=None, prompt_body=None, **overrides):
    """Create an ``Agent Prompt`` (the prompt-template doctype).

    Verified doctype name: NOT "Prompt Template" — it is literally
    ``Agent Prompt`` (`huf/huf/doctype/agent_prompt/agent_prompt.json`), used
    as the ``options`` target of `Agent.agent_prompt`/`Agent.copied_from_prompt`
    (`huf/huf/doctype/agent/agent.json`) and resolved by
    `huf/ai/prompt_resolver.py::resolve_prompt` (walks `prompt_group` via
    `_get_locked_version_body(..., doctype="Agent Prompt")`).

    Required fields per the doctype JSON: ``title`` (Data, reqd=1),
    ``prompt_body`` (Code, reqd=1). ``visibility`` defaults to "Private" per
    the doctype's own default — left unset here to exercise that default
    unless a test overrides it.
    """
    fields = {
        "doctype": "Agent Prompt",
        "title": title or f"Test Prompt {_hash()}",
        "prompt_body": prompt_body or "You are a deterministic test prompt.",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Agent Tool Function
# ---------------------------------------------------------------------------


def make_agent_tool_function(tool_name=None, tool_type=None, **overrides):
    """Create an ``Agent Tool Function``.

    Required fields per `huf/huf/doctype/agent_tool_function/agent_tool_function.json`:
    ``tool_name`` (Data, reqd=1), ``description`` (Small Text, reqd=1),
    ``tool_type`` (Link -> Agent Tool Type, reqd=1). ``tool_type`` has no
    static option list (it's a Link to a separate ``Agent Tool Type``
    doctype, not a Select) — if not supplied, we resolve any existing
    ``Agent Tool Type`` row, or create a minimal one, so this factory stays
    self-sufficient on a bare site.

    ``types`` (Select) is the tool's execution-kind field (Custom Function /
    HTTP GET / CRUD op / etc.) — left unset by default since the doctype
    does not require it; pass e.g. `types="Custom Function"` for tests that
    need a specific handler path.

    ``Agent Tool Type``'s own single required field is confirmed, verified
    from `huf/huf/doctype/agent_tool_type/agent_tool_type.json`, to be
    ``name1`` (Data, reqd=1) — an unusually-named field (not `tool_type_name`
    or `title`), used as-is here.
    """
    if tool_type is None:
        existing = frappe.db.get_value("Agent Tool Type", {}, "name")
        if existing:
            tool_type = existing
        else:
            tt = frappe.get_doc(
                {
                    "doctype": "Agent Tool Type",
                    "name1": f"test-tool-type-{_hash()}",
                }
            )
            tt.insert(ignore_permissions=True)
            tool_type = tt.name

    fields = {
        "doctype": "Agent Tool Function",
        "tool_name": tool_name or f"test_tool_{_hash()}",
        "description": "Deterministic test tool function.",
        "tool_type": tool_type,
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Deterministic test-tool fixtures (huf/ai/test_tools.py)
# ---------------------------------------------------------------------------
#
# Two flavors, for the two test layers this repo distinguishes
# (docs/testing/CURRENT_STATE.md):
#
# - ``build_*_tool_spec()`` return a plain dict shaped like the fields Frappe
#   would read off an ``Agent Tool Function`` document. Layer A (mocked-
#   frappe, no bench — huf/ai/tests/test_test_tools.py) tests wrap these in
#   ``types.SimpleNamespace`` to feed attribute-access-only code
#   (``PermissionAwareToolRegistry``/``create_function_tool``) without a real
#   DB.
# - ``create_*_tool_doc()`` build on top of ``make_agent_tool_function()``
#   above to actually insert a real ``Agent Tool Function`` document, for
#   Layer B/C (real-bench) tests that need to exercise the full assembly ->
#   permission-check -> handler-resolution -> handler-call ->
#   persistence path end to end.
#
# Each handler in huf/ai/test_tools.py has one builder pair here, keyed by a
# short handler name in ``TEST_TOOL_SPEC_BUILDERS``.

import json as _json

_TEST_TOOL_FUNCTION_MODULE = "huf.ai.test_tools"


def _build_test_tool_spec(tool_name, description, function_path, **overrides):
    parameters = overrides.pop("parameters", {"type": "object", "properties": {}})
    spec = {
        "doctype": "Agent Tool Function",
        "tool_name": tool_name,
        "types": "Custom Function",
        "description": description,
        "function_path": function_path,
        "params": _json.dumps(parameters),
        "required_permission": overrides.pop("required_permission", None),
        "reference_doctype": overrides.pop("reference_doctype", None),
        "allowed_for_guest": overrides.pop("allowed_for_guest", 0),
        "is_read_only": overrides.pop("is_read_only", 0),
    }
    spec.update(overrides)
    return spec


def build_echo_tool_spec(**overrides):
    """Spec for ``huf.ai.test_tools.echo`` — returns its input unchanged."""
    return _build_test_tool_spec(
        tool_name=overrides.pop("tool_name", "test_echo"),
        description="Test tool: returns its input arguments unchanged.",
        function_path=f"{_TEST_TOOL_FUNCTION_MODULE}.echo",
        parameters={"type": "object", "properties": {}, "additionalProperties": True},
        is_read_only=1,
        **overrides,
    )


def build_deterministic_add_tool_spec(**overrides):
    """Spec for ``huf.ai.test_tools.deterministic_add`` — sums a list of numbers."""
    return _build_test_tool_spec(
        tool_name=overrides.pop("tool_name", "test_deterministic_add"),
        description="Test tool: deterministically sums a list of numbers.",
        function_path=f"{_TEST_TOOL_FUNCTION_MODULE}.deterministic_add",
        parameters={
            "type": "object",
            "properties": {"numbers": {"type": "array", "items": {"type": "number"}}},
            "required": ["numbers"],
        },
        is_read_only=1,
        **overrides,
    )


def build_deterministic_fail_tool_spec(**overrides):
    """Spec for ``huf.ai.test_tools.deterministic_fail`` — always raises."""
    return _build_test_tool_spec(
        tool_name=overrides.pop("tool_name", "test_deterministic_fail"),
        description="Test tool: always raises a known exception (failure-path testing).",
        function_path=f"{_TEST_TOOL_FUNCTION_MODULE}.deterministic_fail",
        parameters={"type": "object", "properties": {}},
        is_read_only=1,
        **overrides,
    )


def build_permission_protected_mutation_tool_spec(**overrides):
    """Spec for ``huf.ai.test_tools.permission_protected_mutation``.

    Sets ``required_permission="write"`` plus a real ``reference_doctype``
    ("ToDo") so the actual ``TOOL_PERMISSIONS``/``required_permission`` gate
    in ``PermissionAwareToolRegistry._can_use_tool`` (huf/ai/tool_registry.py:
    91-105) is exercised — that gate only runs when ``reference_doctype`` is
    set.
    """
    return _build_test_tool_spec(
        tool_name=overrides.pop("tool_name", "test_permission_protected_mutation"),
        description="Test tool: mutation gated on write permission for a reference doctype.",
        function_path=f"{_TEST_TOOL_FUNCTION_MODULE}.permission_protected_mutation",
        parameters={
            "type": "object",
            "properties": {"record_id": {"type": "string"}, "value": {"type": "string"}},
            "required": ["record_id", "value"],
        },
        required_permission=overrides.pop("required_permission", "write"),
        reference_doctype=overrides.pop("reference_doctype", "ToDo"),
        **overrides,
    )


def build_slow_or_timeout_tool_spec(**overrides):
    """Spec for ``huf.ai.test_tools.slow_or_timeout`` — capped, deterministic sleep."""
    return _build_test_tool_spec(
        tool_name=overrides.pop("tool_name", "test_slow_or_timeout"),
        description="Test tool: sleeps for a capped, deterministic duration (timeout-path testing).",
        function_path=f"{_TEST_TOOL_FUNCTION_MODULE}.slow_or_timeout",
        parameters={
            "type": "object",
            "properties": {"duration": {"type": "number", "description": "Seconds to sleep, capped at 2.0"}},
        },
        is_read_only=1,
        **overrides,
    )


TEST_TOOL_SPEC_BUILDERS = {
    "echo": build_echo_tool_spec,
    "deterministic_add": build_deterministic_add_tool_spec,
    "deterministic_fail": build_deterministic_fail_tool_spec,
    "permission_protected_mutation": build_permission_protected_mutation_tool_spec,
    "slow_or_timeout": build_slow_or_timeout_tool_spec,
}


def build_all_test_tool_specs():
    """Convenience: {handler_name: spec_dict} for every test tool in the family."""
    return {name: builder() for name, builder in TEST_TOOL_SPEC_BUILDERS.items()}


def create_test_tool_doc(handler_name, insert=True, **overrides):
    """Real-bench (Layer B/C) helper: build the spec for ``handler_name`` and
    insert it via ``make_agent_tool_function`` above. Idempotent — reuses an
    existing doc with the same ``tool_name`` rather than erroring on the
    ``unique`` constraint, so repeated test runs don't need manual cleanup.
    """
    if handler_name not in TEST_TOOL_SPEC_BUILDERS:
        raise ValueError(f"Unknown test tool handler: {handler_name}")

    spec = TEST_TOOL_SPEC_BUILDERS[handler_name](**overrides)

    if not insert:
        return spec

    existing = frappe.db.get_value("Agent Tool Function", {"tool_name": spec["tool_name"]}, "name")
    if existing:
        return frappe.get_doc("Agent Tool Function", existing)

    spec.pop("doctype", None)
    tool_name = spec.pop("tool_name")
    return make_agent_tool_function(tool_name=tool_name, **spec)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------


def make_mcp_server(server_name=None, **overrides):
    """Create an ``MCP Server``.

    Required fields per `huf/huf/doctype/mcp_server/mcp_server.json`:
    ``server_name`` (Data, reqd=1), ``transport_type`` (Select, reqd=1,
    default "http"), ``server_url`` (Data, reqd=1).

    Controller `validate()` (`huf/huf/doctype/mcp_server/mcp_server.py:9-13`)
    additionally requires ``auth_header_name`` whenever ``auth_type`` is set
    to anything other than "none"/"oauth" — the doctype's own default for
    ``auth_type`` is "oauth", so leaving it at that default (unset here)
    satisfies the controller without needing ``auth_header_name``.
    """
    fields = {
        "doctype": "MCP Server",
        "server_name": server_name or f"Test MCP Server {_hash()}",
        "transport_type": "http",
        "server_url": f"https://example.invalid/mcp/{_hash()}",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def make_agent(agent_name=None, provider=None, model=None, instructions=None, **overrides):
    """Create a minimal valid ``Agent``.

    Required field per `huf/huf/doctype/agent/agent.json`: ``agent_name``
    (Data, reqd=1). ``agent_modality`` defaults to "Both" per the doctype's
    own default. ``provider``/``model`` are Links (not `reqd=1` at the
    schema level) but every existing test in this repo always supplies them
    together (see `test_agent.py` throughout) since most controller/runtime
    code paths assume a resolvable model; if not supplied, this factory
    creates a fresh linked (AI Provider, AI Model) pair via
    `make_ai_provider_and_model()` so it is self-sufficient on a bare site.

    ``instructions`` is the Local-mode prompt body (see
    `huf/ai/prompt_resolver.py::resolve_prompt` — Local mode returns
    `agent_doc.instructions` directly); ``prompt_mode`` defaults to "Local"
    per the doctype, so this is the field that actually matters for a
    minimal agent's behavior, not `agent_prompt` (Template mode only).
    """
    if provider is None or model is None:
        auto_provider, auto_model = make_ai_provider_and_model()
        provider = provider or auto_provider
        model = model or auto_model

    fields = {
        "doctype": "Agent",
        "agent_name": agent_name or f"test-agent-{_hash()}",
        "provider": provider,
        "model": model,
        "instructions": instructions or "You are a deterministic test agent.",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_agent_with_tools_and_prompt(
    agent_name=None,
    provider=None,
    model=None,
    tool_functions=None,
    agent_prompt=None,
    mcp_servers=None,
    **overrides,
):
    """Create an ``Agent`` variant wired to tools + a Template-mode prompt.

    - ``agent_tool`` child table (options: "Agent Tool",
      `huf/huf/doctype/agent/agent.json`) rows reference `Agent Tool Function`
      docs via child fieldname ``tool`` (mirrors
      `huf/huf/doctype/agent/test_agent.py:279`,
      `agent.append("agent_tool", {"tool": tools[0]})`).
    - ``agent_mcp_server`` child table rows reference `MCP Server` docs via
      child fieldname ``mcp_server`` — verified against
      `huf/huf/doctype/agent_mcp_server/agent_mcp_server.json`
      (`mcp_server` Link -> MCP Server, plus `enabled`/`server_url`/`tool_count`
      denormalized fields not needed here).
    - Setting ``prompt_mode="Template"`` + ``agent_prompt=<Agent Prompt name>``
      switches `resolve_prompt()` onto the Template-mode path
      (`huf/ai/prompt_resolver.py`), which is exactly what distinguishes this
      variant from the plain `make_agent()` minimal case.

    If ``tool_functions``/``agent_prompt``/``mcp_servers`` are not supplied,
    one of each is created via the other factories in this module so the
    variant is self-sufficient on a bare site.
    """
    if tool_functions is None:
        tool_functions = [make_agent_tool_function().name]
    if agent_prompt is None:
        agent_prompt = make_agent_prompt().name
    if mcp_servers is None:
        mcp_servers = [make_mcp_server().name]

    base_overrides = dict(overrides)
    base_overrides.setdefault("prompt_mode", "Template")
    base_overrides["agent_prompt"] = agent_prompt

    doc_fields = {
        "doctype": "Agent",
        "agent_name": agent_name or f"test-agent-tooled-{_hash()}",
    }
    if provider is None or model is None:
        auto_provider, auto_model = make_ai_provider_and_model()
        provider = provider or auto_provider
        model = model or auto_model
    doc_fields["provider"] = provider
    doc_fields["model"] = model
    doc_fields.update(base_overrides)

    doc = frappe.get_doc(doc_fields)
    for tool_name in tool_functions:
        doc.append("agent_tool", {"tool": tool_name})
    for mcp_name in mcp_servers:
        doc.append("agent_mcp_server", {"mcp_server": mcp_name})

    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Agent Conversation / Agent Run
# ---------------------------------------------------------------------------


def make_agent_conversation(agent=None, session_id=None, **overrides):
    """Create an ``Agent Conversation``.

    Required field per `huf/huf/doctype/agent_conversation/agent_conversation.json`:
    ``session_id`` (Data, reqd=1). ``agent``/``model`` are Links, not
    doctype-`reqd=1`, but a conversation with no `agent` is not meaningful for
    any regression test — if not supplied, an agent is created via
    `make_agent()`. ``status`` defaults to "Active" per the doctype.
    The controller (`agent_conversation.py`) is a 9-line stub with no
    `validate()` logic — all behavior lives in
    `huf/ai/conversation_manager.py`, per `CURRENT_STATE.md` section 6.
    """
    if agent is None:
        agent = make_agent().name

    fields = {
        "doctype": "Agent Conversation",
        "agent": agent,
        "session_id": session_id or f"test-session-{_hash(12)}",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_agent_run(conversation=None, agent=None, provider=None, model=None, **overrides):
    """Create an ``Agent Run``.

    No field is `reqd=1` in `huf/huf/doctype/agent_run/agent_run.json` itself
    — every field is optional at the schema level. However the controller's
    `validate()` (`huf/huf/doctype/agent_run/agent_run.py:9-31`) enforces a
    conditional invariant: if `reference_doctype` is set it must be a real
    DocType, and if `reference_name` is set `reference_doctype` must also be
    set and resolvable — this factory leaves both unset by default to avoid
    that check entirely (a minimal run has no document reference).

    Despite no field being schema-required, a run with no `agent`/`conversation`
    is not meaningful for any actual regression test, so both are created via
    `make_agent()`/`make_agent_conversation()` if not supplied — matching this
    module's stated goal of letting tests build a deterministic world rather
    than constructing degenerate documents.

    ``status`` has no default in the doctype (blank/"" is a valid initial
    state); pass e.g. `status="Success"` for tests that need a terminal run.
    ``run_kind`` defaults to "agent" per the doctype.
    """
    if agent is None:
        agent = make_agent(provider=provider, model=model)
        agent_name = agent.name
        provider = provider or agent.provider
        model = model or agent.model
    else:
        agent_name = agent

    if conversation is None:
        conversation = make_agent_conversation(agent=agent_name).name

    fields = {
        "doctype": "Agent Run",
        "agent": agent_name,
        "conversation": conversation,
    }
    if provider:
        fields["provider"] = provider
    if model:
        fields["model"] = model
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Automation (new runtime) / Agent Trigger (legacy) — both live per
# CURRENT_STATE.md section 7's dual-doctype finding.
# ---------------------------------------------------------------------------


def make_automation(automation_name=None, agent=None, instruction=None, **overrides):
    """Create an ``Automation`` (the current/new automation-runtime doctype).

    Required fields per `huf/huf/doctype/automation/automation.json`:
    ``automation_name`` (Data, reqd=1), ``agent`` (Link -> Agent, reqd=1),
    ``instruction`` (Long Text, reqd=1). ``status`` defaults to "Draft".

    This is distinct from the legacy per-Agent ``Agent Trigger`` doctype
    (see `make_agent_trigger()` below) — `Automation` is the parent entity;
    its actual firing conditions live on child ``Automation Trigger`` rows
    (see `make_automation_trigger()`), run via
    `huf/ai/automation_runner.py::run_automation` per
    `docs/testing/CURRENT_STATE.md` section 7.
    """
    if agent is None:
        agent = make_agent().name

    fields = {
        "doctype": "Automation",
        "automation_name": automation_name or f"Test Automation {_hash()}",
        "agent": agent,
        "instruction": instruction or "Run the deterministic test scenario.",
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_automation_trigger(automation=None, trigger_name=None, trigger_type="Manual", **overrides):
    """Create an ``Automation Trigger`` (child/companion doctype of ``Automation``).

    Required fields per `huf/huf/doctype/automation_trigger/automation_trigger.json`:
    ``trigger_name`` (Data, reqd=1), ``automation`` (Link -> Automation,
    reqd=1). ``trigger_type`` defaults to "Manual" here — the least
    conditionally-demanding option (Schedule/Doc Event/Webhook triggers all
    pull in further conditionally-required fields — `schedule_type`,
    `reference_doctype`+`doc_event`, `allowed_methods`+`auth_mode`
    respectively — not enforced by any `reqd=1` in the JSON itself, but
    real-world-meaningless without them; pass a specific `trigger_type` plus
    its companion fields as overrides for tests that need those trigger
    kinds).
    """
    if automation is None:
        automation = make_automation().name

    fields = {
        "doctype": "Automation Trigger",
        "trigger_name": trigger_name or f"Test Trigger {_hash()}",
        "automation": automation,
        "trigger_type": trigger_type,
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


def make_agent_trigger(agent=None, trigger_name=None, trigger_type="Manual", **overrides):
    """Create a legacy ``Agent Trigger`` (per-Agent trigger, pre-``Automation``
    runtime split).

    Required fields per `huf/huf/doctype/agent_trigger/agent_trigger.json`:
    ``trigger_name`` (Data, reqd=1), ``agent`` (Link -> Agent, reqd=1).
    Both this doctype and ``Automation``/``Automation Trigger`` are
    confirmed still live on current `develop` (`docs/testing/CURRENT_STATE.md`
    section 7's runtime-flag finding) — support both explicitly rather than
    assuming one has fully replaced the other. Use `make_automation_trigger()`
    for the new runtime, this for legacy-path regression coverage.
    """
    if agent is None:
        agent = make_agent().name

    fields = {
        "doctype": "Agent Trigger",
        "trigger_name": trigger_name or f"Test Legacy Trigger {_hash()}",
        "agent": agent,
        "trigger_type": trigger_type,
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc


# ---------------------------------------------------------------------------
# Knowledge Source
# ---------------------------------------------------------------------------


def make_knowledge_source(source_name=None, knowledge_type="sqlite_fts", **overrides):
    """Create a ``Knowledge Source``.

    Required fields per `huf/huf/doctype/knowledge_source/knowledge_source.json`:
    ``source_name`` (Data, reqd=1), ``knowledge_type`` (Select, reqd=1;
    "sqlite_fts" is the simplest, dependency-free backend per
    `huf/ai/knowledge/backends/` — no external vector-DB connection needed,
    matching the "no bench/external services available" constraint this
    factory set was written under), ``scope`` (Select, reqd=1, default
    "Site" — left at that default), ``storage_mode`` (Select, reqd=1,
    default "Frappe File" — left at that default).
    """
    fields = {
        "doctype": "Knowledge Source",
        "source_name": source_name or f"Test Knowledge Source {_hash()}",
        "knowledge_type": knowledge_type,
    }
    fields.update(overrides)
    doc = frappe.get_doc(fields)
    doc.insert(ignore_permissions=True)
    return doc
