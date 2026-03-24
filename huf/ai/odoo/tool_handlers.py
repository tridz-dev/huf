import frappe
import json
from functools import wraps
import odoo_client_lib as odoo_lib
from .connector import OdooConnector
from .exceptions import OdooAuthError, OdooRateLimitError


def odoo_safe_invoke(f):
	@wraps(f)
	def wrapper(*args, **kwargs):
		try:
			return f(*args, **kwargs)
		except OdooAuthError:
			return {"success": False, "error": "Authentication Failed", "suggestion": "Check Odoo credentials and user permissions."}
		except OdooRateLimitError:
			return {"success": False, "error": "Rate Limit Exceeded", "suggestion": "Odoo SaaS limits reached. Please slow down migrations or high-frequency tasks."}
		except odoo_lib.Error as e:
			return {"success": False, "error": str(e), "suggestion": "Verify model name, fields, and search domains."}
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Odoo Tool Error")
			return {"success": False, "error": str(e)}
	return wrapper


@odoo_safe_invoke
def handle_odoo_search_read(connection: str, model: str, domain: str = None, 
                            fields: str = None, limit: int = 20, 
                            offset: int = 0, order: str = None, **kwargs) -> dict:
    """Search and read records from an Odoo model."""
    connector = OdooConnector(connection)
    
    parsed_domain = json.loads(domain) if domain else []
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    
    records = connector.search_read(
        model=model,
        domain=parsed_domain,
        fields=parsed_fields,
        limit=min(limit, 100),
        offset=offset,
        order=order
    )
    
    # Optional count for UI/Agent context
    total = connector.execute(model, "search_count", parsed_domain)
    
    return {
        "success": True,
        "model": model,
        "records": records,
        "count": len(records),
        "total_count": total,
        "has_more": (offset + len(records)) < total
    }


@odoo_safe_invoke
def handle_odoo_read(connection: str, model: str, ids: str, fields: str = None, **kwargs) -> dict:
    """Read specific records by ID(s)."""
    connector = OdooConnector(connection)
    
    parsed_ids = json.loads(ids) if isinstance(ids, str) and ids.startswith("[") else [int(ids)] if ids else []
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else None
    
    records = connector.execute(model, "read", parsed_ids, parsed_fields)
    
    return {
        "success": True,
        "model": model,
        "records": records
    }


@odoo_safe_invoke
def handle_odoo_create(connection: str, model: str, values: str, **kwargs) -> dict:
    """Create a new Odoo record."""
    connector = OdooConnector(connection)
    
    parsed_values = json.loads(values) if isinstance(values, str) else values
    
    # Blueprint Pattern 2: Process O2M/M2M commands if needed
    # (Simplified for now, expecting model to provide correct format or handled by agent)
    
    record_id = connector.create(model, parsed_values)
    
    return {
        "success": True,
        "model": model,
        "id": record_id,
        "message": f"Successfully created {model} with ID {record_id}"
    }


@odoo_safe_invoke
def handle_odoo_write(connection: str, model: str, ids: str, values: str, **kwargs) -> dict:
    """Update existing Odoo record(s)."""
    connector = OdooConnector(connection)
    
    parsed_ids = json.loads(ids) if isinstance(ids, str) and ids.startswith("[") else [int(ids)]
    parsed_values = json.loads(values) if isinstance(values, str) else values
    
    success = connector.write(model, parsed_ids, parsed_values)
    
    return {
        "success": success,
        "model": model,
        "ids": parsed_ids,
        "message": f"Successfully updated {len(parsed_ids)} records in {model}" if success else "Update failed"
    }


@odoo_safe_invoke
def handle_odoo_unlink(connection: str, model: str, ids: str, **kwargs) -> dict:
    """Delete record(s) from Odoo."""
    connector = OdooConnector(connection)
    
    parsed_ids = json.loads(ids) if isinstance(ids, str) and ids.startswith("[") else [int(ids)]
    
    success = connector.unlink(model, parsed_ids)
    
    return {
        "success": success,
        "model": model,
        "ids": parsed_ids,
        "message": f"Successfully deleted {len(parsed_ids)} records from {model}"
    }


@odoo_safe_invoke
def handle_odoo_execute(connection: str, model: str, method: str, ids: str = None, args: str = None, **kwargs) -> dict:
    """Execute any ORM method (e.g., action_confirm)."""
    connector = OdooConnector(connection)
    
    parsed_ids = json.loads(ids) if ids and ids.startswith("[") else [int(ids)] if ids else None
    parsed_args = json.loads(args) if args else []
    
    params = []
    if parsed_ids is not None:
        params.append(parsed_ids)
    if parsed_args:
        params.extend(parsed_args)
        
    result = connector.execute(model, method, *params)
    
    return {
        "success": True,
        "model": model,
        "method": method,
        "result": result
    }


@odoo_safe_invoke
def handle_odoo_fields_get(connection: str, model: str, **kwargs) -> dict:
    """Get field metadata for an Odoo model."""
    connector = OdooConnector(connection)
    
    fields = connector.fields_get(model)
    
    return {
        "success": True,
        "model": model,
        "fields": fields
    }


@odoo_safe_invoke
def handle_odoo_list_models(connection: str, **kwargs) -> dict:
    """List available models in Odoo."""
    connector = OdooConnector(connection)
    
    models = connector.get_models()
    
    return {
        "success": True,
        "models": models,
        "count": len(models)
    }


@odoo_safe_invoke
def handle_odoo_search_count(connection: str, model: str, domain: str = None, **kwargs) -> dict:
    """Count records matching a domain in an Odoo model."""
    connector = OdooConnector(connection)
    parsed_domain = json.loads(domain) if domain else []
    count = connector.execute(model, "search_count", parsed_domain)
    return {
        "success": True,
        "model": model,
        "count": count
    }


@odoo_safe_invoke
def handle_odoo_read_group(connection: str, model: str, domain: str = None,
                           fields: str = None, groupby: str = None,
                           limit: int = 80, offset: int = 0,
                           orderby: str = None, **kwargs) -> dict:
    """Read grouped/aggregated data from an Odoo model."""
    connector = OdooConnector(connection)
    parsed_domain = json.loads(domain) if domain else []
    parsed_fields = [f.strip() for f in fields.split(",")] if fields else []
    parsed_groupby = [g.strip() for g in groupby.split(",")] if groupby else []

    if not parsed_fields or not parsed_groupby:
        return {"success": False, "error": "Both 'fields' and 'groupby' are required."}

    result = connector.execute(
        model, "read_group",
        parsed_domain,
        fields=parsed_fields,
        groupby=parsed_groupby,
        limit=limit,
        offset=offset,
        orderby=orderby
    )
    return {
        "success": True,
        "model": model,
        "groups": result,
        "count": len(result)
    }
