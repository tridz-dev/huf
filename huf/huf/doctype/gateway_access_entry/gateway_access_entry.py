import frappe
from frappe.model.document import Document


class GatewayAccessEntry(Document):
    """Canonical, auditable sender or room admission entry."""

    def on_update(self):
        doc_before_save = self.get_doc_before_save()
        if self.state == "Approved" and doc_before_save and doc_before_save.state != "Approved":
            try:
                from huf.ai.gateway_webhook import get_gateway_adapter
                from huf.ai.gateway_adapters.types import GatewayReply

                gw_doc = frappe.get_doc("Gateway", self.gateway)
                if gw_doc.integration_settings:
                    adapter = get_gateway_adapter(gw_doc)
                    
                    target_conv = self.external_id
                    target_thread = None
                    recent_events = frappe.get_all(
                        "Gateway Event",
                        filters={"gateway": self.gateway, "sender_id": self.external_id},
                        fields=["conversation_id", "thread_id"],
                        order_by="creation desc",
                        limit=1
                    )
                    if recent_events and recent_events[0].conversation_id:
                        target_conv = recent_events[0].conversation_id
                        target_thread = recent_events[0].thread_id

                    welcome_text = (
                        "🎉 Your access pairing request has been approved!\n\n"
                        "You can now interact directly with this assistant."
                    )
                    adapter.send_reply(GatewayReply(
                        conversation_id=target_conv, 
                        text=welcome_text,
                        thread_id=target_thread or None,
                        reply_to_provider_message_id=target_thread or None,
                    ))
            except Exception as exc:
                err_msg = str(exc)
                if hasattr(exc, "response") and hasattr(exc.response, "text"):
                    err_msg += f" - Response: {exc.response.text}"
                frappe.log_error("Failed to send welcome message on manual approval", f"{err_msg}\n{frappe.get_traceback()}")
