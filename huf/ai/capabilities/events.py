"""Doc Event capability descriptors and Trigger Builder adapter for HUF app capability discovery.

Maps Frappe DocType lifecycle events (as exposed by the ``Agent Trigger`` doctype's
``doc_event`` Select field) into capability descriptors, and provides a pure mapping
function that turns an event capability id back into the field payload expected by
an ``Agent Trigger`` "Doc Event" record.
"""

from frappe import ValidationError

from huf.ai.capabilities.models import make_capability_descriptor

# Human-friendly labels for the small set of doc events we recommend by default.
# Technical values are the real `doc_event` Select options from
# huf/huf/doctype/agent_trigger/agent_trigger.json (verified against the JSON;
# all five of the plan's §8.2 placeholders matched the real Select options
# exactly, so no substitutions were needed).
CANONICAL_EVENT_LABELS = {
    "Created": "after_insert",
    "Changed": "on_update",
    "Submitted": "on_submit",
    "Cancelled": "on_cancel",
    "Deleted": "on_trash",
}

# The remaining raw doc_event Select options from agent_trigger.json, exposed
# for advanced users. Each maps the technical event name to a title-cased
# display label.
ADVANCED_EVENT_LABELS = {
    "before_insert": "Before Insert",
    "validate": "Validate",
    "before_save": "Before Save",
    "after_save": "After Save",
    "before_submit": "Before Submit",
    "after_submit": "After Submit",
    "before_rename": "Before Rename",
    "after_rename": "After Rename",
    "after_delete": "After Delete",
}


def generate_events_for_resource(app_name, doctype, include_advanced=False, submittable=False):
    """Build event capability descriptors for a doctype's lifecycle events.

    This is a pure function: it does not call frappe.get_meta or otherwise touch
    the database. Callers (e.g. resources.py) are expected to determine whether
    the doctype is submittable and pass that in via `submittable`, so this
    function stays testable in isolation.

    Args:
        app_name: the source app owning the doctype (used as source_app).
        doctype: the reference doctype name.
        include_advanced: if True, also emit descriptors for ADVANCED_EVENT_LABELS.
        submittable: if False, "Submitted"/"Cancelled" entries are skipped since
            those doc events only fire for submittable doctypes.

    Returns:
        A list of capability descriptor dicts (kind="event").
    """
    descriptors = []

    for human_label, technical_event in CANONICAL_EVENT_LABELS.items():
        if human_label in ("Submitted", "Cancelled") and not submittable:
            continue
        descriptors.append(
            _build_event_descriptor(
                app_name=app_name,
                doctype=doctype,
                human_label=human_label,
                technical_event=technical_event,
                advanced=False,
            )
        )

    if include_advanced:
        for technical_event, human_label in ADVANCED_EVENT_LABELS.items():
            descriptors.append(
                _build_event_descriptor(
                    app_name=app_name,
                    doctype=doctype,
                    human_label=human_label,
                    technical_event=technical_event,
                    advanced=True,
                )
            )

    return descriptors


def _build_event_descriptor(*, app_name, doctype, human_label, technical_event, advanced):
    """Build a single event capability descriptor. Internal helper."""
    return make_capability_descriptor(
        kind="event",
        source_app=app_name,
        source_type="generated",
        source_key=f"{doctype}.{technical_event}",
        title=f"{human_label}",
        resource_doctype=doctype,
        event_name=technical_event,
        visibility="advanced" if advanced else "recommended",
        actionability="actionable_now",
        mutation_level="read",
    )


def build_trigger_payload(app_name, doctype, event_capability_id, condition=None, prompt_field=None):
    """Map an event capability id into Agent Trigger "Doc Event" field values.

    This is the Trigger Builder Adapter described in the plan (§21): a pure
    mapping function. It does NOT create or save an Agent Trigger document.

    Args:
        app_name: the source app the capability id was minted for (unused in the
            payload itself, kept for symmetry with other adapters and for callers
            that want to verify the capability id's app segment).
        doctype: the doctype the caller expects this trigger to target.
        event_capability_id: a capability id of the form
            "event:{app}:{doctype}.{technical_event}".
        condition: optional Frappe safe_eval condition to place on the trigger.
        prompt_field: optional fieldname supplying the agent's instructions.

    Returns:
        A plain dict shaped like the Agent Trigger "Doc Event" fields:
        {"trigger_type": "Doc Event", "reference_doctype": ..., "doc_event": ...,
         "condition": ..., "prompt_field": ...}

    Raises:
        frappe.ValidationError: if the doctype parsed out of event_capability_id
            does not match the `doctype` argument.
    """
    try:
        _kind, _app, source_key = event_capability_id.split(":", 2)
        parsed_doctype, technical_event = source_key.rsplit(".", 1)
    except ValueError:
        raise ValidationError(f"Malformed event capability id: {event_capability_id!r}")

    if parsed_doctype != doctype:
        raise ValidationError(
            f"Capability id {event_capability_id!r} is for doctype {parsed_doctype!r}, "
            f"not {doctype!r}"
        )

    return {
        "trigger_type": "Doc Event",
        "reference_doctype": doctype,
        "doc_event": technical_event,
        "condition": condition,
        "prompt_field": prompt_field,
    }
