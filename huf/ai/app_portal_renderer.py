"""Page renderer for a HUF App's own per-app ``www/`` portal template.

Turns a manifest's `route` from inert launcher metadata (Phase 1's state)
into something HUF actually serves, for whichever provider app declares a
`www_template` (see doc/features/apps/delivery-portal-vs-desk.md, "Path A --
Portal page", gap list item 2).

Structural pattern mirrors huf.ai.app_public_renderer.HufAppPublicRenderer
(BaseRenderer subclass, can_render()/render() only) and, one level down,
huf.ai.app_seeding.scanner.find_seed_dirs(): a provider app ships its
template entirely under its own source tree
(`<app>/<app>/www/<www_template>/` or `<app>/www/<www_template>/`, see
scanner.find_www_template_dir), never under the shared `huf/www/`. HUF is
never modified to add a new portal page -- exactly the same "discovered, not
user-authored" contract app-pattern.md describes for seed directories.

Unlike HufAppPublicRenderer (which delegates to Frappe's own TemplatePage to
re-render the *same* fixed `huf` SPA shell for every alias), this renderer
resolves and renders a *different* template per app, so it cannot delegate
to TemplatePage's cross-app `www/` search -- that search matches by filename
only, first match wins across *all* installed apps, with no way to pin it to
one specific provider app. Instead this renderer resolves the provider app's
own template directory directly (via find_www_template_dir) and renders it
with frappe.render_template, sidestepping TemplatePage entirely -- so it does
not repeat the app_public_renderer.py bug where TemplatePage.render() was
called without first checking can_render() (fixed alongside this phase; see
that module's render() for the guard).

Boot context: reuses huf.www.huf.build_boot_context() -- the same
Guest-branching CSRF+boot-data pattern the `/huf` SPA shell and
`/huf/apps/<alias>` public renderer already stand on -- so a portal
template's own Jinja/JS can read `{{ boot }}` / `{{ csrf_token }}` exactly
like huf/www/huf.html does, with no second boot mechanism to maintain.
"""

import os

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer

from huf.ai.app_seeding.scanner import find_www_template_dir
from huf.www.huf import build_boot_context


class HufAppPortalRenderer(BaseRenderer):
	"""Page renderer that serves a provider app's own portal template.

	Routes: any site path that exactly matches an `enabled=1`,
	`sync_status="Active"` `HUF App.route` whose `www_template` is set.
	Tried before Frappe's built-in TemplatePage/StaticPage/etc (see
	`page_renderer` order in huf/hooks.py), so a provider app's declared
	route is served without needing a static `website_route_rules` entry --
	the registry itself is the routing table, discovered the same way
	`find_seed_dirs()` discovers seed directories.
	"""

	def can_render(self) -> bool:
		return self._resolve_app() is not None

	def _resolve_app(self):
		route = "/" + self.path.strip("/")
		return frappe.db.get_value(
			"HUF App",
			{
				"route": route,
				"enabled": 1,
				"sync_status": "Active",
				"www_template": ["!=", ""],
			},
			["name", "source_app", "www_template", "agent"],
			as_dict=True,
		)

	def render(self):
		app = self._resolve_app()
		if not app:
			# can_render() already gates this, but render() must never crash
			# if the record disappears between the two calls (e.g. a
			# concurrent disable/delete) -- degrade the same way every other
			# "not actually servable" case in this renderer family does.
			raise frappe.PageDoesNotExistError

		template_dir = find_www_template_dir(app.source_app, app.www_template)
		if template_dir is None:
			# Manifest declared a www_template that resolved fine at sync
			# time but the directory has since gone missing on disk (app
			# upgraded/reinstalled without it, etc). Log for whoever owns
			# the provider app; still fail as "not found" to the visitor
			# rather than a 500.
			frappe.log_error(
				title="HUF App Portal Renderer",
				message=(
					f"HUF App '{app.name}' declares www_template "
					f"'{app.www_template}' under source app '{app.source_app}', "
					"but the directory could not be resolved on disk."
				),
			)
			raise frappe.PageDoesNotExistError

		context = frappe._dict()
		context.update(build_boot_context())
		context.app_id = app.name
		context.agent = app.agent or ""

		context = self._apply_pymodule_context(app.source_app, app.www_template, context)

		index_path = os.path.join(template_dir, "index.html")
		with open(index_path, encoding="utf-8") as f:
			source = f.read()

		html = frappe.render_template(source, context)
		return self.build_response(html)

	@staticmethod
	def _apply_pymodule_context(source_app: str, www_template: str, context):
		"""Colocated ``index.py:get_context(context)`` override, mirroring
		Frappe's own TemplatePage.set_pymodule()/update_context() convention
		(doc/reference/frappe-framework/portal/context.md) -- only supported
		for the package-root location (`<app>/<app>/www/<www_template>/`),
		since that is the location the resulting dotted module path
		(`<source_app>.www.<www_template>.index`) can actually import from.
		Optional: a template with no index.py just gets the shared boot
		context above and nothing else.
		"""
		pymodule_name = f"{source_app}.www.{www_template}.index"
		try:
			app_path = frappe.get_app_path(source_app)
		except Exception:
			return context
		pymodule_path = os.path.join(app_path, "www", www_template, "index.py")
		if not os.path.isfile(pymodule_path):
			return context
		try:
			pymodule = frappe.get_module(pymodule_name)
		except Exception as e:
			frappe.log_error(
				title="HUF App Portal Renderer",
				message=f"Failed to import colocated {pymodule_name}: {e}",
			)
			return context
		if hasattr(pymodule, "get_context"):
			try:
				data = pymodule.get_context(context)
				if data:
					context.update(data)
			except Exception as e:
				frappe.log_error(
					title="HUF App Portal Renderer",
					message=f"get_context() in {pymodule_name} raised: {e}",
				)
		return context
