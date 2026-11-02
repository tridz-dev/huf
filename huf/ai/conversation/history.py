"""Pure helpers that slice a conversation history without splitting a tool-call group.

``huf.ai.conversation_manager`` re-exports these names.
"""


def _is_tool_message(msg) -> bool:
    """Return True if the context message represents a tool result."""
    return isinstance(msg, dict) and msg.get("role") == "tool"


def _tool_call_ids_from_assistant(msg: dict) -> list:
    """Extract tool_call ids from an assistant message."""
    if not isinstance(msg, dict):
        return []
    ids = []
    for tc in msg.get("tool_calls") or []:
        tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        if tc_id:
            ids.append(tc_id)
    return ids


def _tool_call_group_intervals(history: list) -> list:
    """
    Return intervals (start_index, end_index) of assistant/tool-call groups.
    A group starts at the assistant message that declared a tool_call and ends
    at the last matching role='tool' result message.
    """
    if not history:
        return []

    declarations = {}
    for idx, msg in enumerate(history):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            for cid in _tool_call_ids_from_assistant(msg):
                if cid not in declarations:
                    declarations[cid] = idx

    intervals = []
    seen = set()
    for idx, msg in enumerate(history):
        if isinstance(msg, dict) and msg.get("role") == "tool":
            cid = msg.get("tool_call_id")
            if cid and cid in declarations and cid not in seen:
                start = declarations[cid]
                intervals.append((start, idx))
                seen.add(cid)
    return intervals


def safe_history_slice(history: list, limit: int) -> list:
    """
    Return the last `limit` messages without splitting tool-call pairs.

    OpenAI requires every role='tool' message to follow an assistant message
    that declared the matching tool_call. A naive slice can drop the assistant
    message while keeping its tool results, causing BadRequestError. This
    helper shifts the cut point backward until it no longer starts inside a
    tool-call result group.
    """
    if not history or len(history) <= limit:
        return history

    intervals = _tool_call_group_intervals(history)

    cut_index = len(history) - limit
    # Move cut point backward while it would start inside an open tool-call group
    while cut_index > 0:
        inside = any(start < cut_index <= end for start, end in intervals)
        if not inside:
            break
        cut_index -= 1

    return history[cut_index:]


def safe_history_split(history: list, split_index: int) -> tuple:
    """
    Split history into (left, right) at a boundary that does not break
    assistant/tool-call pairs. The right (remaining) part is guaranteed not
    to start with an orphaned tool message.
    """
    if not history:
        return [], []

    if split_index <= 0:
        return [], list(history)

    if split_index >= len(history):
        return list(history), []

    intervals = _tool_call_group_intervals(history)

    # Move split backward while it would leave the right side starting inside a group
    while split_index > 0:
        inside = any(start < split_index <= end for start, end in intervals)
        if not inside:
            break
        split_index -= 1

    return history[:split_index], history[split_index:]
