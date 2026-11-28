import json

import frappe

from huf.ai.handlers.crud import _check_doctype_allowed, _read_denied, _readable_name, _type_read_allowed
from huf.ai.tools.functions import (
    get_report_result,
    attach_file_to_document,
    send_email,
)

logger = frappe.logger("huf")


def handle_get_report_result(report_name: str, filters: dict | None = None, limit: int | None = None, ignore_permissions=False, **kwargs):
    _meta, _guard_err = _check_doctype_allowed("Report", read_only=True)
    if _guard_err:
        return json.loads(_guard_err)

    if not ignore_permissions and not (_type_read_allowed("Report") and _readable_name("Report", report_name)):
        return _read_denied("Report")
    return get_report_result(report_name, filters=filters, limit=limit, user=frappe.session.user)


def handle_attach_file_to_document(reference_doctype, document_id, **kwargs):
    """
    SDK handler that wraps attach_file_to_document.
    """
    if not reference_doctype or not document_id:
        return {
            "success": False,
            "error": "reference_doctype and document_id are required"
        }

    _meta, _guard_err = _check_doctype_allowed(reference_doctype)
    if _guard_err:
        return json.loads(_guard_err)

    normalized_kwargs = {}
    for k, v in (kwargs or {}).items():
        if k in ["file_path", "file_url"]:
            normalized_kwargs[k] = v
            continue

        if isinstance(v, str):
            normalized_kwargs[k] = v

    try:
        result = attach_file_to_document(
            reference_doctype,
            document_id,
            **normalized_kwargs,
        )
        return {"success": True, "result": result}
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_attach_file_to_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_send_email(to=None, subject=None, message=None, body=None, reference_doctype=None, reference_name=None, gateway=None, **kwargs):
    """
    SDK handler that wraps send_email. Accepts 'message' or 'body' for the email content.
    """
    if not reference_doctype:
        reference_doctype = frappe.flags.get("current_function_doctype")

    try:
        return send_email(
            to=to,
            subject=subject,
            message=message or body,
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            gateway=gateway,
        )
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_send_email failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}
