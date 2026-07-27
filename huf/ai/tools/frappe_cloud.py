import json

import frappe
import httpx

from huf.ai.tools.credentials import get_credential, update_last_error

logger = frappe.logger("huf")
SERVICE_NAME = "frappe_cloud"


def _get_fc_headers():
	api_key = get_credential(SERVICE_NAME, "api_key")
	api_secret = get_credential(SERVICE_NAME, "api_secret")
	if not api_key or not api_secret:
		raise ValueError("Frappe Cloud credentials not configured")

	return {
		"Authorization": f"token {api_key}:{api_secret}",
		"Accept": "application/json",
		"Content-Type": "application/json",
	}


def _get_base_url():
	server_url = get_credential(SERVICE_NAME, "server_url") or "https://cloud.frappe.io"
	return f"{server_url.rstrip('/')}/api/method"


def _make_fc_request(method: str, endpoint: str, json_data=None, params=None):
	response = httpx.request(
		method,
		f"{_get_base_url()}/{endpoint}",
		headers=_get_fc_headers(),
		json=json_data,
		params=params,
		timeout=30,
	)
	response.raise_for_status()
	return response.json() if response.text else {}


def _success(results=None) -> str:
	return json.dumps({"success": True, "results": results if results is not None else {}})


def _failure(action: str, error: Exception) -> str:
	error_msg = f"Frappe Cloud {action} Error: {error!s}"
	logger.warning(error_msg)
	update_last_error(SERVICE_NAME, error_msg)
	return json.dumps({"success": False, "error": str(error)}, default=str)


def _message(data):
	return data.get("message", {})


def _compact(data, fields=None):
	if not fields:
		return data
	if isinstance(data, list):
		return [{field: item.get(field) for field in fields if isinstance(item, dict) and field in item} for item in data]
	if isinstance(data, dict):
		return {field: data.get(field) for field in fields if field in data}
	return data


def _result(data, kwargs, fields=None):
	message = _message(data)
	if kwargs.get("full") or kwargs.get("debug"):
		return _success(message)
	return _success(_compact(message, fields))


def _required(kwargs, *keys):
	missing = [key for key in keys if not kwargs.get(key)]
	if missing:
		return f"{', '.join(missing)} {'are' if len(missing) > 1 else 'is'} required"
	return None


def handle_fc_list_benches(**kwargs) -> str:
	try:
		data = _make_fc_request("POST", "press.api.bench.all", json_data={"bench_filter": kwargs.get("filters")})
		return _result(data, kwargs, fields=("name", "title", "version", "status", "number_of_sites", "number_of_apps"))
	except Exception as e:
		return _failure("List Benches", e)


def handle_fc_get_bench(**kwargs) -> str:
	try:
		name = kwargs.get("bench") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "bench is required"})
		data = _make_fc_request("POST", "press.api.bench.get", json_data={"name": name})
		return _result(data, kwargs, fields=("name", "title", "version", "status", "no_sites", "creation"))
	except Exception as e:
		return _failure("Get Bench", e)


def handle_fc_create_bench(**kwargs) -> str:
	try:
		title = kwargs.get("title")
		version = kwargs.get("version", "Version 16")
		cluster = kwargs.get("cluster", "UAE")
		apps = kwargs.get("apps") or [{"name": "frappe", "source": kwargs.get("frappe_source", "SRC-frappe-237")}]
		if not title:
			return json.dumps({"success": False, "error": "title is required"})
		data = _make_fc_request(
			"POST",
			"press.api.bench.new",
			json_data={"bench": {"title": title, "version": version, "cluster": cluster, "apps": apps}},
		)
		return _success(_message(data))
	except Exception as e:
		return _failure("Create Bench", e)


def handle_fc_archive_bench(**kwargs) -> str:
	try:
		name = kwargs.get("bench") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "bench is required"})
		data = _make_fc_request("POST", "press.api.bench.archive", json_data={"name": name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Archive Bench", e)


def handle_fc_add_app_to_bench(**kwargs) -> str:
	try:
		bench = kwargs.get("bench") or kwargs.get("name")
		app = kwargs.get("app")
		source = kwargs.get("source")
		if not bench or not app or not source:
			return json.dumps({"success": False, "error": "bench, app, and source are required"})
		data = _make_fc_request("POST", "press.api.bench.add_app", json_data={"name": bench, "app": app, "source": source})
		return _success(_message(data))
	except Exception as e:
		return _failure("Add App To Bench", e)


def handle_fc_list_sites(**kwargs) -> str:
	try:
		data = _make_fc_request("POST", "press.api.site.all", json_data={"site_filter": kwargs.get("filters")})
		return _result(data, kwargs, fields=("name", "status", "group", "bench", "cluster", "version", "creation"))
	except Exception as e:
		return _failure("List Sites", e)


def handle_fc_site_options(**kwargs) -> str:
	try:
		data = _make_fc_request("POST", "press.api.site.options_for_new", json_data={"for_bench": kwargs.get("bench")})
		if kwargs.get("full") or kwargs.get("debug"):
			return _success(_message(data))
		message = _message(data)
		return _success(
			{
				"versions": message.get("versions", []),
				"domain": message.get("domain"),
				"providers": message.get("providers", []),
				"closest_cluster": message.get("closest_cluster"),
			}
		)
	except Exception as e:
		return _failure("Site Options", e)


def handle_fc_site_plans(**kwargs) -> str:
	try:
		data = _make_fc_request("POST", "press.api.site.get_plans", json_data={"rg": kwargs.get("bench")})
		plans = _message(data) or []
		return _success(
			[
				{
					"name": plan.get("name"),
					"price_usd": plan.get("price_usd"),
					"private_benches": plan.get("private_benches"),
				}
				for plan in plans
			]
		)
	except Exception as e:
		return _failure("Site Plans", e)


def handle_fc_create_site(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		if not site_name:
			return json.dumps({"success": False, "error": "site_name is required"})

		site = {
			"name": site_name,
			"apps": kwargs.get("apps") or ["frappe"],
			"version": kwargs.get("version", "Version 16"),
			"domain": kwargs.get("domain", "frappe.cloud"),
			"plan": kwargs.get("plan", "USD 5"),
		}
		if kwargs.get("bench"):
			site["group"] = kwargs["bench"]
		for key in ("provider", "cluster"):
			if kwargs.get(key):
				site[key] = kwargs[key]

		data = _make_fc_request("POST", "press.api.site.new", json_data={"site": site})
		return _success(_message(data))
	except Exception as e:
		return _failure("Create Site", e)


def handle_fc_drop_site(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		if not site_name:
			return json.dumps({"success": False, "error": "site_name is required"})
		data = _make_fc_request("POST", "press.api.site.archive", json_data={"name": site_name, "force": kwargs.get("force", True)})
		return _success(_message(data))
	except Exception as e:
		return _failure("Drop Site", e)


def handle_fc_backup_site(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		data = _make_fc_request("POST", "press.api.site.backup", json_data={"name": site_name, "with_files": kwargs.get("with_files", False)})
		return _success(_message(data))
	except Exception as e:
		return _failure("Backup Site", e)


def handle_fc_download_backup(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		data = _make_fc_request("POST", "press.api.site.backups", json_data={"name": site_name})
		return _result(data, kwargs, fields=("name", "status", "with_files", "database_size", "creation", "offsite"))
	except Exception as e:
		return _failure("Download Backup", e)


def handle_fc_migrate_site(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		data = _make_fc_request("POST", "press.api.site.migrate", json_data={"name": site_name, "skip_failing_patches": kwargs.get("skip_failing_patches", False)})
		return _success(_message(data))
	except Exception as e:
		return _failure("Migrate Site", e)


def handle_fc_clear_cache(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		data = _make_fc_request("POST", "press.api.site.clear_cache", json_data={"name": site_name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Clear Cache", e)


def handle_fc_update_site(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		data = _make_fc_request("POST", "press.api.site.update", json_data={"name": site_name, "skip_backups": kwargs.get("skip_backups", False)})
		return _success(_message(data))
	except Exception as e:
		return _failure("Update Site", e)


def handle_fc_clone_site(**kwargs) -> str:
	try:
		source_site = kwargs.get("source_site")
		bench = kwargs.get("bench")
		if not source_site or not bench:
			return json.dumps({"success": False, "error": "source_site and bench are required"})
		data = _make_fc_request("POST", "press.api.site.clone", json_data={"source_site": source_site, "bench": bench})
		return _success(_message(data))
	except Exception as e:
		return _failure("Clone Site", e)


def handle_fc_add_app_to_site(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		app = kwargs.get("app")
		if not site_name or not app:
			return json.dumps({"success": False, "error": "site_name and app are required"})
		data = _make_fc_request("POST", "press.api.site.install_app", json_data={"name": site_name, "app": app, "plan": kwargs.get("plan")})
		return _success(_message(data))
	except Exception as e:
		return _failure("Add App To Site", e)


def handle_fc_get_admin_login_link(**kwargs) -> str:
	try:
		site_name = kwargs.get("site_name") or kwargs.get("name")
		data = _make_fc_request("POST", "press.api.site.login", json_data={"name": site_name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Get Admin Login Link", e)


def handle_fc_list_webhooks(**kwargs) -> str:
	try:
		filters = {}
		if kwargs.get("endpoint"):
			filters["endpoint"] = kwargs["endpoint"]
		data = _make_fc_request(
			"POST",
			"press.api.client.get_list",
			json_data={
				"doctype": "Press Webhook",
				"fields": ["name", "endpoint", "enabled"],
				"filters": filters,
				"limit": kwargs.get("limit", 20),
			},
		)
		return _result(data, kwargs, fields=("name", "endpoint", "enabled"))
	except Exception as e:
		return _failure("List Webhooks", e)


def handle_fc_available_webhook_events(**kwargs) -> str:
	try:
		data = _make_fc_request("POST", "press.api.webhook.available_events")
		return _result(data, kwargs, fields=("name", "description"))
	except Exception as e:
		return _failure("Available Webhook Events", e)


def handle_fc_add_webhook(**kwargs) -> str:
	try:
		if error := _required(kwargs, "endpoint", "secret", "events"):
			return json.dumps({"success": False, "error": error})
		data = _make_fc_request(
			"POST",
			"press.api.webhook.add",
			json_data={"endpoint": kwargs["endpoint"], "secret": kwargs["secret"], "events": kwargs["events"]},
		)
		return _success(_message(data))
	except Exception as e:
		return _failure("Add Webhook", e)


def handle_fc_update_webhook(**kwargs) -> str:
	try:
		if error := _required(kwargs, "name", "endpoint", "events"):
			return json.dumps({"success": False, "error": error})
		data = _make_fc_request(
			"POST",
			"press.api.webhook.update",
			json_data={
				"name": kwargs["name"],
				"endpoint": kwargs["endpoint"],
				"secret": kwargs.get("secret", ""),
				"events": kwargs["events"],
			},
		)
		return _success(_message(data))
	except Exception as e:
		return _failure("Update Webhook", e)


def handle_fc_delete_webhook(**kwargs) -> str:
	try:
		if error := _required(kwargs, "name"):
			return json.dumps({"success": False, "error": error})
		data = _make_fc_request(
			"POST",
			"press.api.client.delete",
			json_data={"doctype": "Press Webhook", "name": kwargs["name"]},
		)
		return _success(_message(data))
	except Exception as e:
		return _failure("Delete Webhook", e)


def handle_fc_list_ssh_keys(**kwargs) -> str:
	try:
		data = _make_fc_request("POST", "press.api.account.get_user_ssh_keys")
		return _result(data, kwargs, fields=("name", "ssh_fingerprint", "creation", "is_default"))
	except Exception as e:
		return _failure("List SSH Keys", e)


def handle_fc_add_ssh_key(**kwargs) -> str:
	try:
		if error := _required(kwargs, "key"):
			return json.dumps({"success": False, "error": error})
		data = _make_fc_request("POST", "press.api.account.add_key", json_data={"key": kwargs["key"]})
		return _success(_message(data))
	except Exception as e:
		return _failure("Add SSH Key", e)


def handle_fc_mark_ssh_key_default(**kwargs) -> str:
	try:
		key_name = kwargs.get("key_name") or kwargs.get("name")
		if not key_name:
			return json.dumps({"success": False, "error": "key_name is required"})
		data = _make_fc_request("POST", "press.api.account.mark_key_as_default", json_data={"key_name": key_name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Mark SSH Key Default", e)


def handle_fc_get_bench_ssh_certificate(**kwargs) -> str:
	try:
		bench = kwargs.get("bench") or kwargs.get("name")
		if not bench:
			return json.dumps({"success": False, "error": "bench is required"})
		data = _make_fc_request("POST", "press.api.bench.certificate", json_data={"name": bench})
		return _result(data, kwargs, fields=("name", "valid_until", "certificate_type", "group", "user_ssh_key"))
	except Exception as e:
		return _failure("Get Bench SSH Certificate", e)


def handle_fc_generate_bench_ssh_certificate(**kwargs) -> str:
	try:
		bench = kwargs.get("bench") or kwargs.get("name")
		if not bench:
			return json.dumps({"success": False, "error": "bench is required"})
		data = _make_fc_request("POST", "press.api.bench.generate_certificate", json_data={"name": bench})
		return _result(data, kwargs, fields=("name", "valid_until", "certificate_type", "group", "user_ssh_key"))
	except Exception as e:
		return _failure("Generate Bench SSH Certificate", e)
