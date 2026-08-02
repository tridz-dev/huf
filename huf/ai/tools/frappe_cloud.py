import json
from types import SimpleNamespace

import frappe
import httpx

logger = frappe.logger("huf")
SERVICE_NAME = "frappe_cloud"


class _FCAccount(SimpleNamespace):
	"""Lightweight wrapper around the active Frappe Cloud integration settings."""

	def save(self, ignore_permissions=False):
		if self._doc:
			self._doc.last_error = self.last_error
			self._doc.save(ignore_permissions=ignore_permissions)


def _get_fc_account():
	"""Return the active/default Frappe Cloud Integration Settings as an account wrapper."""
	settings = frappe.get_all(
		"Integration Settings",
		filters={"service": SERVICE_NAME, "is_active": 1},
		fields=["name"],
		order_by="is_default DESC, modified DESC",
		limit=1,
	)
	if not settings:
		raise ValueError("No active Frappe Cloud integration configured")

	doc = frappe.get_doc("Integration Settings", settings[0].name)
	creds = {}
	for row in doc.credentials or []:
		creds[row.key] = row.get_password("value") or row.value

	api_key = creds.get("api_key")
	api_secret = creds.get("api_secret")
	if not api_key or not api_secret:
		raise ValueError("Frappe Cloud API key/secret not configured")

	return _FCAccount(
		_doc=doc,
		server_url=creds.get("server_url") or "https://cloud.frappe.io",
		api_key=api_key,
		api_secret=api_secret,
		last_error=doc.last_error,
	)


def _update_fc_last_error(error: str):
	"""Persist the last error on the active Frappe Cloud integration."""
	try:
		account = _get_fc_account()
		account.last_error = error[:140]
		account.save(ignore_permissions=True)
	except Exception:
		pass


def _get_fc_headers():
	account = _get_fc_account()
	return {
		"Authorization": f"token {account.api_key}:{account.api_secret}",
		"Accept": "application/json",
		"Content-Type": "application/json",
	}


def _get_base_url():
	account = _get_fc_account()
	return f"{account.server_url.rstrip('/')}/api/method"


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
	_update_fc_last_error(error_msg)
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
		version = kwargs.get("version")
		cluster = kwargs.get("cluster")
		apps = kwargs.get("apps")
		server = kwargs.get("server")
		if not title:
			return json.dumps({"success": False, "error": "title is required"})
		if not version or not cluster:
			return json.dumps({"success": False, "error": "version and cluster are required"})
		if not apps:
			return json.dumps({"success": False, "error": "apps is required (list of {name, source})"})
		bench_payload = {"title": title, "version": version, "cluster": cluster, "apps": apps}
		if server:
			bench_payload["server"] = server
		data = _make_fc_request("POST", "press.api.bench.new", json_data={"bench": bench_payload})
		return _success(_message(data))
	except Exception as e:
		return _failure("Create Bench", e)


def handle_fc_bench_options(**kwargs) -> str:
	"""Return available versions, clusters and apps for creating a new bench."""
	try:
		data = _make_fc_request("POST", "press.api.bench.options")
		return _result(data, kwargs, fields=("versions", "clusters"))
	except Exception as e:
		return _failure("Bench Options", e)


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
		version = kwargs.get("version")
		domain = kwargs.get("domain")
		plan = kwargs.get("plan")
		if not site_name:
			return json.dumps({"success": False, "error": "site_name is required"})
		if not version or not domain or not plan:
			return json.dumps({"success": False, "error": "version, domain, and plan are required"})

		site = {
			"name": site_name,
			"apps": kwargs.get("apps") or ["frappe"],
			"version": version,
			"domain": domain,
			"plan": plan,
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


# ---------------------------------------------------------------------------
# Server-level tools
# ---------------------------------------------------------------------------


def handle_fc_list_servers(**kwargs) -> str:
	"""List Frappe Cloud application and database servers."""
	try:
		filters = kwargs.get("filters") or {}
		data = _make_fc_request("POST", "press.api.server.all", json_data={"server_filter": filters})
		return _result(
			data,
			kwargs,
			fields=("name", "title", "status", "creation", "cluster", "plan", "app_server", "region_info"),
		)
	except Exception as e:
		return _failure("List Servers", e)


def handle_fc_get_server(**kwargs) -> str:
	"""Get details of a Frappe Cloud server (App or Database server)."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		data = _make_fc_request("POST", "press.api.server.get", json_data={"name": name})
		return _result(
			data,
			kwargs,
			fields=("name", "title", "status", "team", "cluster", "region_info", "type", "app_server"),
		)
	except Exception as e:
		return _failure("Get Server", e)


def handle_fc_get_server_overview(**kwargs) -> str:
	"""Get plan and ownership overview for a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		data = _make_fc_request("POST", "press.api.server.overview", json_data={"name": name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Get Server Overview", e)


def handle_fc_server_options(**kwargs) -> str:
	"""Return regions and plans available for creating a new Frappe Cloud server."""
	try:
		data = _make_fc_request("POST", "press.api.server.options")
		return _result(data, kwargs, fields=("regions", "app_plans", "db_plans", "plan_types"))
	except Exception as e:
		return _failure("Server Options", e)


def handle_fc_server_plans(**kwargs) -> str:
	"""List Frappe Cloud server plans for a given server type."""
	try:
		server_type = kwargs.get("server_type") or "Server"
		cluster = kwargs.get("cluster")
		platform = kwargs.get("platform")
		payload = {"name": server_type}
		if cluster:
			payload["cluster"] = cluster
		if platform:
			payload["platform"] = platform
		data = _make_fc_request("POST", "press.api.server.plans", json_data=payload)
		message = _message(data) or {}
		plans = message.get("plans", [])
		return _success(
			[
				{
					"name": plan.get("name"),
					"title": plan.get("title"),
					"price_usd": plan.get("price_usd"),
					"vcpu": plan.get("vcpu"),
					"memory": plan.get("memory"),
					"disk": plan.get("disk"),
					"platform": plan.get("platform"),
				}
				for plan in plans
			]
		)
	except Exception as e:
		return _failure("Server Plans", e)


def handle_fc_create_server(**kwargs) -> str:
	"""Create a new Frappe Cloud server (unified app + database by default)."""
	try:
		title = kwargs.get("title")
		cluster = kwargs.get("cluster")
		app_plan = kwargs.get("app_plan")
		if not title or not cluster or not app_plan:
			return json.dumps({"success": False, "error": "title, cluster, and app_plan are required"})

		server_payload = {
			"title": title,
			"cluster": cluster,
			"app_plan": app_plan,
			"auto_increase_storage": kwargs.get("auto_increase_storage", False),
		}

		db_plan = kwargs.get("db_plan")
		if db_plan:
			# Separate app + database server mode
			server_payload["db_plan"] = db_plan
			endpoint = "press.api.server.new"
		else:
			endpoint = "press.api.server.new_unified"

		data = _make_fc_request("POST", endpoint, json_data={"server": server_payload})
		return _success(_message(data))
	except Exception as e:
		return _failure("Create Server", e)


def handle_fc_archive_server(**kwargs) -> str:
	"""Archive/delete a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		data = _make_fc_request("POST", "press.api.server.archive", json_data={"name": name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Archive Server", e)


def handle_fc_reboot_server(**kwargs) -> str:
	"""Reboot a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		data = _make_fc_request("POST", "press.api.server.reboot", json_data={"name": name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Reboot Server", e)


def handle_fc_rename_server(**kwargs) -> str:
	"""Rename (change the title of) a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		title = kwargs.get("title")
		if not name or not title:
			return json.dumps({"success": False, "error": "server and title are required"})
		data = _make_fc_request("POST", "press.api.server.rename", json_data={"name": name, "title": title})
		return _success(_message(data))
	except Exception as e:
		return _failure("Rename Server", e)


def handle_fc_change_server_plan(**kwargs) -> str:
	"""Resize/change the plan of a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		plan = kwargs.get("plan")
		if not name or not plan:
			return json.dumps({"success": False, "error": "server and plan are required"})
		data = _make_fc_request("POST", "press.api.server.change_plan", json_data={"name": name, "plan": plan})
		return _success(_message(data))
	except Exception as e:
		return _failure("Change Server Plan", e)


def handle_fc_server_usage(**kwargs) -> str:
	"""Get current CPU, memory and disk usage for a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		data = _make_fc_request("POST", "press.api.server.usage", json_data={"name": name})
		return _success(_message(data))
	except Exception as e:
		return _failure("Server Usage", e)


def handle_fc_list_server_benches(**kwargs) -> str:
	"""List benches (release groups) running on a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		data = _make_fc_request("POST", "press.api.server.groups", json_data={"name": name})
		return _result(
			data,
			kwargs,
			fields=("name", "title", "version", "status", "number_of_sites", "number_of_apps"),
		)
	except Exception as e:
		return _failure("List Server Benches", e)


def handle_fc_list_server_jobs(**kwargs) -> str:
	"""List Agent jobs for a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		payload = {"filters": {"server": name}}
		for key in ("order_by", "limit_start", "limit_page_length"):
			if kwargs.get(key):
				payload[key] = kwargs[key]
		data = _make_fc_request("POST", "press.api.server.jobs", json_data=payload)
		return _result(
			data,
			kwargs,
			fields=("name", "job_type", "creation", "status", "start", "end", "duration"),
		)
	except Exception as e:
		return _failure("List Server Jobs", e)


def handle_fc_list_server_plays(**kwargs) -> str:
	"""List Ansible plays for a Frappe Cloud server."""
	try:
		name = kwargs.get("server") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "server is required"})
		payload = {"filters": {"server": name}}
		for key in ("order_by", "limit_start", "limit_page_length"):
			if kwargs.get(key):
				payload[key] = kwargs[key]
		data = _make_fc_request("POST", "press.api.server.plays", json_data=payload)
		return _result(
			data,
			kwargs,
			fields=("name", "play", "creation", "status", "start", "end", "duration"),
		)
	except Exception as e:
		return _failure("List Server Plays", e)


def handle_fc_list_bench_jobs(**kwargs) -> str:
	"""List Agent jobs for a Frappe Cloud bench/release group."""
	try:
		name = kwargs.get("bench") or kwargs.get("name")
		if not name:
			return json.dumps({"success": False, "error": "bench is required"})
		payload = {"filters": {"bench": name}}
		for key in ("order_by", "limit_start", "limit_page_length"):
			if kwargs.get(key):
				payload[key] = kwargs[key]
		data = _make_fc_request("POST", "press.api.bench.jobs", json_data=payload)
		return _result(
			data,
			kwargs,
			fields=("name", "job_type", "creation", "status", "start", "end", "duration"),
		)
	except Exception as e:
		return _failure("List Bench Jobs", e)


def handle_fc_list_marketplace_apps(**kwargs) -> str:
	"""List apps available on the Frappe Cloud Marketplace."""
	try:
		filters = kwargs.get("filters") or {}
		limit = kwargs.get("limit", 50)
		data = _make_fc_request(
			"POST",
			"press.api.marketplace.get_apps",
			json_data={"filters": filters, "limit": limit},
		)
		return _result(data, kwargs, fields=("name", "title", "description", "image", "publisher"))
	except Exception as e:
		return _failure("List Marketplace Apps", e)
