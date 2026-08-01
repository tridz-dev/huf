from huf.ai.tool_registry import PermissionAwareToolRegistry

# Guest-allowed tools of these types MUST pin a reference_doctype; otherwise the
# LLM could supply an arbitrary doctype and, combined with the guest
# ignore_permissions bypass, reach data outside the tool's intended scope.
_GUEST_DOCTYPE_PINNED_TYPES = {
    "Get Document",
    "Get Multiple Documents",
    "Get List",
    "Create Document",
    "Create Multiple Documents",
    "Update Document",
    "Update Multiple Documents",
    "Delete Document",
    "Delete Multiple Documents",
    "Attach File to Document",
}

MUTATING_TOOL_TYPES = PermissionAwareToolRegistry.MUTATING_TOOL_TYPES
