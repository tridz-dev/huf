import frappe
from frappe import _, client
from frappe.utils.file_manager import save_file
import os
from urllib.parse import urlparse
import requests



def get_document(doctype: str, document_id: str):
	
	"""
	Get a document from the database
	"""
	# Use the frappe.client.get method to get the document with permissions (both read and field level read)
	return client.get(doctype, name=document_id)


def get_documents(doctype: str, document_ids: list):
	
	"""
	Get documents from the database
	"""
	docs = []
	for document_id in document_ids:
		# Use the frappe.client.get method to get the document with permissions applied
		docs.append(client.get(doctype, name=document_id))
	return docs


def create_document(doctype: str, data: dict, function=None):
	"""
	Create a document in the database
	"""
	if function:
		# Get any default values
		for param in function.parameters:
			if param.default_value:
				# Check if this value was not to be asked by the AI
				if param.do_not_ask_ai:
					data[param.fieldname] = param.default_value

				# Check if the value was not provided
				if not data.get(param.fieldname):
					data[param.fieldname] = param.default_value

	doc = frappe.get_doc({"doctype": doctype, **data})
	doc.insert()
	return {"document_id": doc.name, "message": "Document created", "doctype": doctype}


def create_documents(doctype: str, data: list, function=None):
    """
    Create multiple documents.
    Returns created document_ids and a summary.
    """
    created_ids = []
    errors = []

    for idx, item in enumerate(data or []):
        try:
            res = create_document(doctype, item, function)
            if not res or not res.get("document_id"):
                raise Exception("Create returned no document_id")
            created_ids.append(res["document_id"])
        except Exception as e:
            errors.append({"index": idx, "error": str(e)})

    return {
        "success": len(errors) == 0,
        "doctype": doctype,
        "document_ids": created_ids,
        "errors": errors,
        "message": f"Created {len(created_ids)} document(s)"
    }



def update_document(doctype: str, document_id: str, data: dict, tool=None):
    """
    Update a document in the database with proper error handling
    
    Args:
        doctype: DocType name
        document_id: Document ID to update
        data: Dictionary of fields to update
        tool: Optional tool reference for default values
    """
    try:
        if not doctype or not document_id:
            return {"success": False, "error": "Doctype and document_id are required"}
            
        if not frappe.db.exists(doctype, document_id):
            return {"success": False, "error": f"{doctype} {document_id} not found"}
            
        doc = frappe.get_doc(doctype, document_id)
        
        # Apply default values from tool if available
        if tool:
            for param in tool.parameters:
                if param.default_value and not data.get(param.fieldname):
                    data[param.fieldname] = param.default_value
        
        doc.update(data)
        doc.save()
        
        return {
            "success": True,
            "message": f"{doctype} {document_id} updated successfully",
            "document": doc.as_dict()
        }
    except Exception as e:
        frappe.log_error(f"Error updating {doctype} {document_id}: {str(e)}")
        return {"success": False, "error": str(e)}

def update_documents(doctype: str, data: list, function=None):
    """
    Update multiple documents.
    Each item must contain 'document_id' (or 'name') and the fields to update.
    """
    updated_ids = []
    errors = []

    for idx, doc in enumerate(data or []):
        try:
            payload = dict(doc or {})
            document_id = payload.pop("document_id", None) or payload.pop("name", None)
            if not document_id:
                raise Exception("Missing 'document_id' (or 'name') in item")

            res = update_document(doctype, document_id, payload, function)
            if not res or not res.get("success"):
                raise Exception((res or {}).get("error") or "Unknown error")
            updated_ids.append(res["document"]["name"])
        except Exception as e:
            errors.append({"index": idx, "error": str(e)})

    return {
        "success": len(errors) == 0,
        "doctype": doctype,
        "document_ids": updated_ids,
        "errors": errors,
        "message": f"Updated {len(updated_ids)} document(s)"
    }



def delete_document(doctype: str, document_id: str):
    """
    Delete a document with proper error handling
    
    Args:
        doctype: DocType name
        document_id: Document ID to delete
    """
    try:
        if not doctype or not document_id:
            return {"success": False, "error": "Doctype and document_id are required"}
            
        if not frappe.db.exists(doctype, document_id):
            return {"success": False, "error": f"{doctype} {document_id} not found"}
            
        frappe.delete_doc(doctype, document_id)
        return {"success": True, "message": f"{doctype} {document_id} deleted successfully"}
    except Exception as e:
        frappe.log_error(f"Error deleting {doctype} {document_id}: {str(e)}")
        return {"success": False, "error": str(e)}

def delete_documents(doctype: str, document_ids: list):
	"""
	Delete documents from the database
	"""
	for document_id in document_ids:
		frappe.delete_doc(doctype, document_id)
	return {"document_ids": document_ids, "message": "Documents deleted", "doctype": doctype}


def submit_document(doctype: str, document_id: str):
	"""
	Submit a document in the database
	"""
	doc = frappe.get_doc(doctype, document_id)
	doc.submit()
	return {
		"document_id": document_id,
		"message": f"{doctype} {document_id} submitted",
		"doctype": doctype,
	}


def cancel_document(doctype: str, document_id: str):
	"""
	Cancel a document in the database
	"""
	doc = frappe.get_doc(doctype, document_id)
	doc.cancel()
	return {
		"document_id": document_id,
		"message": f"{doctype} {document_id} cancelled",
		"doctype": doctype,
	}


def get_amended_document_id(doctype: str, document_id: str):
	"""
	Get the amended document for a given document
	"""
	amended_doc = frappe.db.exists(doctype, {"amended_from": document_id})
	if amended_doc:
		return amended_doc
	else:
		return {"message": f"{doctype} {document_id} is not amended"}


def get_amended_document(doctype: str, document_id: str):
    """
    Return the amended document (first match) for a given document, if any.
    """
    amended_name = frappe.db.exists(doctype, {"amended_from": document_id})
    if amended_name:
        return client.get(doctype, name=amended_name)
    return {"message": f"{doctype} {document_id} is not amended", "doctype": doctype}

def get_list(doctype: str, filters: dict = None, fields: list = None, limit: int = 20):
	"""
	Get a list of documents from the database
	"""
	if filters is None:
		filters = {}

	if fields is None:
		fields = ["*"]

	else:
		meta = frappe.get_meta(doctype)
		filtered_fields = ["name as document_id"]
		if "title" in fields:
			filtered_fields.append(meta.get_title_field())

		for field in fields:
			if meta.has_field(field) and field not in filtered_fields:
				filtered_fields.append(field)

	# Use the frappe.get_list method to get the list of documents
	return frappe.get_list(doctype, filters=filters, fields=filtered_fields, limit=limit)


def get_value(doctype: str, filters: dict = None, fieldname: str | list = "name"):
	"""
	Returns a value from a document

	        :param doctype: DocType to be queried
	        :param fieldname: Field to be returned (default `name`) - can be a list of fields(str) or a single field(str)
	        :param filters: dict or string for identifying the record
	"""
	meta = frappe.get_meta(doctype)

	if isinstance(fieldname, list):
		for field in fieldname:
			if not meta.has_field(field):
				return {"message": f"Field {field} does not exist in {doctype}"}

		return client.get_value(doctype, filters=filters, fieldname=fieldname)
	else:
		if not meta.has_field(fieldname):
			return {"message": f"Field {fieldname} does not exist in {doctype}"}

		return client.get_value(doctype, filters=filters, fieldname=fieldname)


def set_value(doctype: str, document_id: str, fieldname: str | dict, value: str = None):
	"""
	Set a value in a document

	        :param doctype: DocType to be queried
	        :param document_id: Document ID to be updated
	        :param fieldname: Field to be updated - fieldname string or JSON / dict with key value pair
	        :param value: value if fieldname is JSON

	        Example:
	                client.set_value("Customer", "CUST-00001", {"customer_name": "John Doe", "customer_email": "john.doe@example.com"}) OR
	                client.set_value("Customer", "CUST-00001", "customer_name", "John Doe")
	"""
	if isinstance(fieldname, dict):
		return client.set_value(doctype, document_id, fieldname)
	else:
		return client.set_value(doctype, document_id, fieldname, value)


def get_report_result(
	report_name: str,
	filters: dict = None,
	limit=None,
	user: str = None,
	ignore_prepared_report: bool = False,
	are_default_filters: bool = True,
):
	"""
	Run a report and return the columns and result
	"""
	# fetch the particular report
	report = frappe.get_doc("Report", report_name)
	if not report:
		return {
			"message": f"Report {report_name} is not present in the system. Please create the report first."
		}

	# run the report by using the get_data method and return the columns and result
	columns, data = report.get_data(
		filters=filters,
		limit=limit,
		user=user,
		ignore_prepared_report=ignore_prepared_report,
		are_default_filters=are_default_filters,
	)

	return {"columns": columns, "data": data}

def attach_file_to_document(doctype: str, document_id: str, file_path: str):
    """
    Attach a file to a document in the database
    """
    if not frappe.db.exists(doctype, document_id):
        return {
            "document_id": document_id,
            "message": f"{doctype} with ID {document_id} not found",
            "doctype": doctype,
        }

    file = frappe.get_doc("File", {"file_url": file_path})

    if not file:
        frappe.throw(_("File not found"))

    newFile = frappe.get_doc(
        {
            "doctype": "File",
            "file_url": file_path,
            "attached_to_doctype": doctype,
            "attached_to_name": document_id,
            "folder": file.folder,
            "file_name": file.file_name,
            "is_private": file.is_private,
        }
    )
    newFile.insert()

    return {"document_id": document_id, "message": "File attached", "file_id": newFile.name}

def _download_content(url: str, timeout: int = 30) -> bytes:
    """Download bytes from an http/https url."""

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _create_file_doc_for_local_path(file_url: str, file_name: str):
    """Create a File doc referencing an existing /files/ path."""
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "file_url": file_url,
            "is_private": 0,
        }
    )
    file_doc.insert()
    return file_doc


def _get_existing_file_by_url(file_url: str):
    """Return File doc if a File with file_url exists."""
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if name:
        return frappe.get_doc("File", name)
    return None


def _process_single_attachment(doctype, document_id, file_path):
    """Helper to download/resolve a single file and return its clean local URL."""
    try:
        file_doc = _get_existing_file_by_url(file_path)
        if file_doc is None:
            if file_path.startswith("http://") or file_path.startswith("https://"):
                content = _download_content(file_path)
                filename = os.path.basename(urlparse(file_path).path) or "downloaded_file"
                saved = save_file(filename, content, doctype=None, docname=None, is_private=False)
                if isinstance(saved, (dict, frappe._dict)):
                    file_doc = frappe.get_doc("File", saved.get("name"))
                else:
                    file_doc = saved
            else:
                filename = os.path.basename(file_path)
                file_doc = _create_file_doc_for_local_path(file_path, filename)
        
        clean_url = getattr(file_doc, "file_url", None)
        if not clean_url:
            clean_url = getattr(file_doc, "file_name", file_path)
            
        attached_name = frappe.db.get_value("File", {
            "attached_to_doctype": doctype,
            "attached_to_name": document_id,
            "file_url": clean_url
        }, "name")

        if not attached_name:
            if file_doc.attached_to_name != document_id:
                file_doc.db_set("attached_to_doctype", doctype)
                file_doc.db_set("attached_to_name", document_id)

        if not clean_url and file_doc.file_name:
             return f"/files/{file_doc.file_name}"
        return clean_url

    except Exception as e:
        frappe.log_error(f"Attachment failed for {file_path}: {str(e)}")
        return None


def attach_file_to_document(doctype: str, document_id: str, **kwargs):
    """
    Attach multiple files to a document. 
    kwargs keys are field names, values are file URLs.
    """
    if not frappe.db.exists(doctype, document_id):
        return {"success": False, "error": f"{doctype} {document_id} not found", "document_id": document_id}

    try:
        doc = frappe.get_doc(doctype, document_id)
        if not frappe.has_permission(doctype, ptype="write", doc=doc):
            return {"success": False, "error": "No write permission on target document"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    updates = {}
    attached_files = []
    meta = frappe.get_meta(doctype)
    
    generic_file = kwargs.pop('file_path', None) or kwargs.pop('file_url', None)
    if generic_file:
         url = _process_single_attachment(doctype, document_id, generic_file)
         if url:
             attached_files.append(url)

    for fieldname, file_url_input in kwargs.items():
        if not file_url_input or not isinstance(file_url_input, str):
            continue

        if meta.has_field(fieldname) or fieldname == "image":
            processed_url = _process_single_attachment(doctype, document_id, file_url_input)
            if processed_url:
                updates[fieldname] = processed_url
                attached_files.append(processed_url)

    if updates:
        try:
            frappe.db.set_value(doctype, document_id, updates)
            frappe.db.commit()
        except Exception as e:
            return {
                "success": True, 
                "message": "Files attached but field update failed", 
                "error": str(e),
                "attached": attached_files
            }

    return {
        "success": True,
        "document_id": document_id,
        "message": f"Attached {len(attached_files)} files.",
        "updated_fields": list(updates.keys()),
        "attached_files": attached_files
    }