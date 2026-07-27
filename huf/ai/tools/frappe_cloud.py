import json
import frappe
import httpx
logger = frappe.logger("huf")
from huf.ai.tools.credentials import get_credential, update_last_error

def _get_fc_headers():
    service_name = "frappe_cloud"
    api_key = get_credential(service_name, "api_key")
    api_secret = get_credential(service_name, "api_secret")
    if not api_key or not api_secret:
        raise ValueError("Frappe Cloud credentials not configured")
    
    return {
        "Authorization": f"token {api_key}:{api_secret}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def _get_base_url():
    service_name = "frappe_cloud"
    server_url = get_credential(service_name, "server_url") or "https://frappecloud.com"
    return f"{server_url.rstrip('/')}/api/method"

def _make_fc_request(method: str, endpoint: str, json_data=None, params=None):
    headers = _get_fc_headers()
    url = f"{_get_base_url()}/{endpoint}"
    
    response = httpx.request(
        method,
        url,
        headers=headers,
        json=json_data,
        params=params,
        timeout=30
    )
    response.raise_for_status()
    return response.json() if response.text else {}

def handle_fc_list_benches(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        data = _make_fc_request("GET", "press.api.client.bench.get_all")
        return json.dumps({"success": True, "results": data.get("message", [])})
    except Exception as e:
        error_msg = f"Frappe Cloud List Benches Error: {str(e)}"
        logger.warning(error_msg)
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_list_sites(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        data = _make_fc_request("GET", "press.api.client.site.get_all")
        return json.dumps({"success": True, "results": data.get("message", [])})
    except Exception as e:
        error_msg = f"Frappe Cloud List Sites Error: {str(e)}"
        logger.warning(error_msg)
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_create_site(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        bench = kwargs.get("bench")
        site_name = kwargs.get("site_name")
        if not bench or not site_name:
             return json.dumps({"success": False, "error": "bench and site_name are required"})
        data = _make_fc_request("POST", "press.api.client.site.new", json_data={"bench": bench, "name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        error_msg = f"Frappe Cloud Create Site Error: {str(e)}"
        logger.warning(error_msg)
        update_last_error(service_name, error_msg)
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_drop_site(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("POST", "press.api.client.site.drop", json_data={"name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_backup_site(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("POST", "press.api.client.site.backup", json_data={"name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_download_backup(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("GET", "press.api.client.site.get_backups", params={"site": site_name})
        return json.dumps({"success": True, "results": data.get("message", [])})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_migrate_site(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("POST", "press.api.client.site.migrate", json_data={"name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_clear_cache(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("POST", "press.api.client.site.clear_cache", json_data={"name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_update_site(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("POST", "press.api.client.site.update", json_data={"name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_clone_site(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        source_site = kwargs.get("source_site")
        bench = kwargs.get("bench")
        if not source_site or not bench:
            return json.dumps({"success": False, "error": "source_site and bench are required"})
        data = _make_fc_request("POST", "press.api.client.site.clone", json_data={"source_site": source_site, "bench": bench})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)

def handle_fc_get_admin_login_link(**kwargs) -> str:
    service_name = "frappe_cloud"
    try:
        site_name = kwargs.get("site_name")
        data = _make_fc_request("POST", "press.api.client.site.login", json_data={"name": site_name})
        return json.dumps({"success": True, "results": data.get("message", {})})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, default=str)
