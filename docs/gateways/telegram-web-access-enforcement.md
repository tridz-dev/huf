# Telegram web access: enforcement and revocation

Implemented in `huf/ai/telegram_web_access_enforce.py`; registered as a `before_request` hook. Sessions without a
`tg_origin` marker cost one dict lookup and are otherwise untouched.

## Enforcement (sessions carrying `tg_origin`)

Gateway settings are read from `tg_origin.gateway` (cached ~30 s). Anything not allowed gets HTTP 403, plain text
`Not allowed in a Telegram session`.

- Navigation: GET/HEAD only, to the gateway's allowed path prefixes. Paths are percent-decoded (up to 3 rounds),
  lower-cased, slash-collapsed; traversal (`..`), backslashes and leftover encodings are rejected. Matching is on
  path-segment boundaries (`/app/sales-invoice` matches `/app/sales-invoice/X`, not `/app/sales-invoices`).
- Always allowed: GET/HEAD `/assets/*`, `/files/*`; methods `frappe.ping`, `ping`, `logout`.
- Writes off: `/api/method` only for the default read list plus the gateway's extra read methods (any HTTP verb);
  `/api/resource` GET only; uploads denied.
- Writes on: POST/PUT/DELETE to `/api/method` and `/api/resource` within normal Frappe permissions.
- Always blocked (writes on or off): impersonate, `frappe.core.doctype.user*`, role/permission/system settings/server
  script/data import/system console/backups methods, any request touching the doctypes User, Role, Has Role, DocPerm,
  Custom DocPerm, User Permission, System Settings, Server Script, Client Script, Data Import, System Console, OAuth
  and API key doctypes, Gateway, Telegram Admin Binding, and any request carrying `sid` in form_dict.

Default read methods (verified in the Frappe 16 bench): `frappe.desk.query_report.run|get_script`,
`frappe.client.get|get_list|get_count|get_value`, `frappe.desk.reportview.get|get_count`,
`frappe.desk.form.load.getdoc|getdoctype|get_docinfo`, `frappe.desk.search.search_link|search_widget`,
`frappe.desk.desktop.get_desktop_page`, `frappe.desk.desk_page.getpage`,
`frappe.desk.notifications.get_notification_info`, `frappe.apps.get_apps`. Names that do not exist in Frappe 16 were
dropped (`get_workspace_sidebar_items`, `get_notification_info_for_boot`).

## Revocation

`revoke_binding_sessions(binding, user)` deletes only Sessions rows of the bound user whose data has
`tg_origin.binding == binding`; the user's ordinary sessions are kept. Triggered by: binding `is_active` 1 -> 0,
`role_scope` change (doc_events on update), binding deletion (`on_trash`), and the Telegram `/unbind` command.
