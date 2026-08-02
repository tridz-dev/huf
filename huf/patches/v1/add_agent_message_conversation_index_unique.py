"""Add a unique constraint on (conversation, conversation_index) for Agent Message.

MA-11: prevents duplicate conversation_index values from concurrent inserts.
"""

import frappe


_UNIQ_NAME = "uk_agent_message_conversation_index"


def _repair_duplicates():
    """Find and repair any existing duplicate indices before adding the constraint."""
    duplicates = frappe.db.sql(
        """
        SELECT conversation, conversation_index, COUNT(*) AS cnt
        FROM `tabAgent Message`
        GROUP BY conversation, conversation_index
        HAVING cnt > 1
        """,
        as_dict=True,
    )

    if not duplicates:
        return

    affected_conversations = {d["conversation"] for d in duplicates}

    for conversation in affected_conversations:
        messages = frappe.db.sql(
            """
            SELECT name, conversation_index
            FROM `tabAgent Message`
            WHERE conversation = %s
            ORDER BY conversation_index ASC, creation ASC, name ASC
            """,
            (conversation,),
            as_dict=True,
        )

        for new_index, msg in enumerate(messages, start=1):
            if msg["conversation_index"] != new_index:
                frappe.db.sql(
                    """
                    UPDATE `tabAgent Message`
                    SET conversation_index = %s
                    WHERE name = %s
                    """,
                    (new_index, msg["name"]),
                )

        # Keep the denormalized counter consistent.
        frappe.db.sql(
            """
            UPDATE `tabAgent Conversation`
            SET total_messages = %s
            WHERE name = %s
            """,
            (len(messages), conversation),
        )


def _add_unique_constraint():
    try:
        frappe.db.add_unique("Agent Message", ["conversation", "conversation_index"], _UNIQ_NAME)
    except Exception as error:
        # A previously deployed/manual index must not make migrate fail.
        if "Duplicate key name" not in str(error):
            raise


def execute():
    _repair_duplicates()
    _add_unique_constraint()
