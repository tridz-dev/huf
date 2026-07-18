import frappe

from huf.ai.provider_brands import migrate_legacy_provider_brand


def execute():
	if not frappe.db.has_column("AI Provider", "provider_brand"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabAI Provider`
			ADD COLUMN `provider_brand` varchar(140)
			"""
		)

	if not frappe.db.has_column("Agent", "provider_brand"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabAgent`
			ADD COLUMN `provider_brand` varchar(140)
			"""
		)

	has_slug = frappe.db.has_column("AI Provider", "slug")
	has_chef = frappe.db.has_column("AI Provider", "chef")

	fields = ["name", "provider_name"]
	if has_slug:
		fields.append("slug")
	if has_chef:
		fields.append("chef")
	if frappe.db.has_column("AI Provider", "provider_brand"):
		fields.append("provider_brand")

	providers = frappe.get_all("AI Provider", fields=fields)
	for row in providers:
		if row.get("provider_brand"):
			continue

		brand = migrate_legacy_provider_brand(
			row.get("slug") if has_slug else None,
			row.get("chef") if has_chef else None,
			row.get("provider_name"),
		)
		frappe.db.set_value("AI Provider", row.name, "provider_brand", brand, update_modified=False)

	if frappe.db.has_column("Agent", "provider_brand"):
		agents = frappe.get_all("Agent", fields=["name", "provider"])
		for agent in agents:
			if not agent.provider:
				continue
			brand = frappe.db.get_value("AI Provider", agent.provider, "provider_brand")
			if brand:
				frappe.db.set_value("Agent", agent.name, "provider_brand", brand, update_modified=False)

	frappe.db.commit()
