# Telegram web access: enforcement and revocation

Implemented in `huf/ai/telegram_web_access_enforce.py`; registered as a `before_request` hook. Sessions without a
`tg_origin` marker cost one dict lookup and are otherwise untouched.

## Enforcement (sessions carrying `tg_origin`)

Gateway settings are read from `tg_origin.gateway` (cached ~30 s). Missing, unreadable or disabled gateway
(`is_enabled` or `telegram_web_access_enabled` off) denies everything. The binding must still exist and be active
(cached ~30 s) and the session user must not hold System Manager/Administrator unless the gateway override is on;
in those cases the session is also deleted. A naive or unreadable `session_end` is a 403. Anything not allowed gets
HTTP 403, plain text `Not allowed in a Telegram session`.

- Navigation: GET/HEAD only, to the gateway's allowed path prefixes. Paths are percent-decoded (up to 3 rounds),
  lower-cased, slash-collapsed; traversal (`..`), backslashes and leftover encodings are rejected. Matching is on
  path-segment boundaries (`/app/sales-invoice` matches `/app/sales-invoice/X`, not `/app/sales-invoices`).
- Always allowed: GET/HEAD `/assets/*`, `/files/*`; methods `frappe.ping`, `ping`, `logout`.
- Writes off: `/api/method` only for the default read list plus the gateway's extra read methods (any HTTP verb);
  `/api/resource/<dt>` and `/api/resource/<dt>/<name>` (and `/api/v2/document/...` the same; `/api/v2/doctype/<dt>`)
  GET only, exact shapes, no `run_method`/`cmd`/`method` parameter (Frappe would execute a document method on a
  GET); uploads denied. `/api/v2/method/<doctype>/<method>` (document method call) is always denied.
- Writes on (opt-in denylist): POST/PUT/DELETE to `/api/method`, `/api/resource` and `/api/v2/document` within normal Frappe permissions, except the always-blocked set below.
- Always blocked (writes on or off): impersonate, `frappe.core.doctype.user*`, role/permission/system settings/server
  script/data import/system console/backups methods, any request touching the doctypes User, Role, Has Role, DocPerm,
  Custom DocPerm, User Permission, System Settings, Server Script, Client Script, Data Import, System Console, OAuth
  and API key doctypes, Role/Module Profile, Custom Role, User Type/Group, Webhook, Notification, Auto Email Report, Print Format, Custom Field, Property Setter, Customize Form, DocType, Report, Social Login Key, Connected App, Token Cache, Email Account/Domain, Access Log, Scheduled Job Type, Console Log, Deleted Document (one list: `BLOCKED_DOCTYPES`), Gateway, Telegram Admin Binding, and any request carrying `sid` in form_dict.

`cmd`: Frappe runs `form_dict.cmd` (query string or body) on ANY path, ahead of path routing (`frappe/app.py`). The
guard therefore resolves `cmd` first: it is honoured only on `/` or on `/api/method/<same method>`; any request carrying
`cmd` on another path (resources, `/app`, `/files`, `/assets`) is denied, and a `cmd` that differs from the path method is denied.

Reports: `query_report.run|get_script` (`report_name`) are allowed only when the Report exists and its (or its
reference report's) `ref_doctype` is not blocked. Report code (Script/Query Reports) runs with the report's own
permissions, as for any desk user with report access, so expose only trusted reports. The report page also loads its
Report doc via `getdoc` (doctype Report), allowed under the same check; `Report` stays blocked under `/api/resource`.
Calls made by the report page (verified from `query_report.js`/`model.js`): `getdoc` (Report), `getdoctype`
(ref_doctype), `query_report.get_script`, `query_report.run`; plus `desk_page.getpage`/`client.get_value` elsewhere in desk.

Default read methods (verified in the Frappe 16 bench): `frappe.desk.query_report.run|get_script`,
`frappe.client.get|get_list|get_count|get_value`, `frappe.desk.reportview.get|get_count`,
`frappe.desk.form.load.getdoc|getdoctype|get_docinfo`, `frappe.desk.search.search_link|search_widget`,
`frappe.desk.desktop.get_desktop_page`, `frappe.desk.desk_page.getpage`,
`frappe.desk.notifications.get_notification_info`, `frappe.apps.get_apps`. Names that do not exist in Frappe 16 were
dropped (`get_workspace_sidebar_items`, `get_notification_info_for_boot`).

## Revocation

`revoke_binding_sessions(binding, user)` deletes only Sessions rows of the bound user whose data has
`tg_origin.binding == binding`; the user's ordinary sessions are kept. Triggered by: binding `is_active` 1 -> 0,
`role_scope`, `frappe_user`, `telegram_user_id` or `gateway` change (the previous user's sessions are found via the before-save doc), binding deletion (`on_trash`), and the Telegram `/unbind` command.
