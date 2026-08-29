# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""
Seeds the bundled ERPNext documentation (docs.frappe.io/erpnext — Setup, Data
Model, Configurations, Buying, Selling, Stock, Website) as an optional,
opt-in Skill + Knowledge Source per section.

This mirrors the app-seeding contract used elsewhere in Huf (`Knowledge
Source` seeded via config, `Skill` seeded via a manifest, `skill_knowledge`
linking the two with a Mandatory/Optional mode) but is wired directly from
`huf.install.after_migrate()` rather than through the `huf/knowledge/*.json`
app-seeding scanner in `huf.ai.app_seeding.scanner`, because that scanner
explicitly skips the `huf` app itself (`find_seed_dirs()` — "Skips 'huf'
itself"; it only scans *other* installed apps for a `huf/` seed directory).
Since this content ships as part of Huf, not a third-party provider app, it
seeds itself directly here instead.

Deliberately opt-in: every seeded Skill has `auto_load = 0` and is not
attached to any Agent by this function. A user (or agent builder) attaches
the skill to an Agent themselves via Agent > Skills, which is what makes the
knowledge base "optionally addable," not on-by-default.

Idempotent: safe to call on every `bench migrate`.
- Knowledge Source: created only if a record with that `source_name` doesn't
  already exist (never overwritten after creation).
- Skill: created only if a record with that `skill_name` doesn't already
  exist (never overwritten after creation, so a user's own edits to an
  auto-loaded skill are not clobbered by a later migrate).
- Knowledge Input: created only if a record with that Knowledge Source +
  file_name combination doesn't already exist yet. Knowledge Input's own
  `after_insert` hook (`huf.ai.knowledge.indexer.process_knowledge_input`)
  performs chunking/indexing — this module only creates the raw text
  records and never reimplements that pipeline.
"""

import os

import frappe

logger = frappe.logger("huf")

# One Knowledge Source + Skill per scraped section. Keys match the directory
# names under huf/huf/data/erpnext_docs/.
SECTIONS = {
	"setup": {
		"source_name": "erpnext-setup-docs",
		"skill_name": "erpnext_setup",
		"title": "ERPNext: Setup",
		"description": "Company setup, fiscal year, chart of accounts, users, and initial ERPNext configuration.",
		"instructions": (
			"You have access to ERPNext's official Setup documentation via knowledge search. "
			"Use it to answer questions about Company setup, Fiscal Year, Chart of Accounts, "
			"users, and the recommended order of initial ERPNext configuration. Cite the "
			"specific DocType or page when giving setup steps."
		),
	},
	"data-model": {
		"source_name": "erpnext-data-model-docs",
		"skill_name": "erpnext_data_model",
		"title": "ERPNext: Data Model",
		"description": "Core ERPNext DocTypes, how records relate, and the underlying data model.",
		"instructions": (
			"You have access to ERPNext's official Data Model documentation via knowledge "
			"search. Use it to answer questions about how ERPNext's core DocTypes relate to "
			"each other and the underlying data model. Cite the specific DocType or page when "
			"explaining relationships."
		),
	},
	"configurations": {
		"source_name": "erpnext-configurations-docs",
		"skill_name": "erpnext_configurations",
		"title": "ERPNext: Configurations",
		"description": "Settings and configuration pages across ERPNext modules.",
		"instructions": (
			"You have access to ERPNext's official Configurations documentation via knowledge "
			"search. Use it to answer questions about module settings and configuration options "
			"across ERPNext. Cite the specific DocType or page when giving setup steps."
		),
	},
	"buying": {
		"source_name": "erpnext-buying-docs",
		"skill_name": "erpnext_buying",
		"title": "ERPNext: Buying",
		"description": "Suppliers, Request for Quotation, Purchase Orders, Purchase Receipts, and buying settings.",
		"instructions": (
			"You have access to ERPNext's official Buying documentation via knowledge search. "
			"Use it to answer questions about Suppliers, Request for Quotation, Purchase Orders, "
			"Purchase Receipts, and buying settings. Cite the specific DocType or page when "
			"giving setup steps."
		),
	},
	"selling": {
		"source_name": "erpnext-selling-docs",
		"skill_name": "erpnext_selling",
		"title": "ERPNext: Selling",
		"description": "Customers, Quotations, Sales Orders, pricing, sales teams and commissions.",
		"instructions": (
			"You have access to ERPNext's official Selling documentation via knowledge search. "
			"Use it to answer questions about Customers, Quotations, Sales Orders, Delivery "
			"Notes, pricing rules, price lists, sales persons/partners, and loyalty programs. "
			"Cite the specific DocType or page when giving setup steps."
		),
	},
	"stock": {
		"source_name": "erpnext-stock-docs",
		"skill_name": "erpnext_stock",
		"title": "ERPNext: Stock",
		"description": "Warehouses, stock entries, valuation, batches/serial numbers, and inventory settings.",
		"instructions": (
			"You have access to ERPNext's official Stock documentation via knowledge search. "
			"Use it to answer questions about Warehouses, Stock Entries, stock valuation "
			"methods, Batches, Serial Numbers, and inventory settings. Cite the specific "
			"DocType or page when giving setup steps."
		),
	},
	"website": {
		"source_name": "erpnext-website-docs",
		"skill_name": "erpnext_website",
		"title": "ERPNext: Website",
		"description": "ERPNext's website/e-commerce module, item groups on the web, and portal settings.",
		"instructions": (
			"You have access to ERPNext's official Website documentation via knowledge search. "
			"Use it to answer questions about ERPNext's website/e-commerce module, item groups "
			"on the web, and portal settings. Cite the specific DocType or page when giving "
			"setup steps."
		),
	},
}

SKILL_CATEGORY = "erpnext-docs"
SKILL_CATEGORY_LABEL = "ERPNext Docs"


def _data_dir():
	return os.path.join(frappe.get_app_path("huf"), "huf", "data", "erpnext_docs")


def _ensure_skill_category():
	if frappe.db.exists("Skill Category", SKILL_CATEGORY_LABEL):
		return
	try:
		frappe.get_doc({
			"doctype": "Skill Category",
			"category_name": SKILL_CATEGORY_LABEL,
		}).insert(ignore_permissions=True)
	except Exception as e:
		logger.warning(f"Failed to create Skill Category '{SKILL_CATEGORY_LABEL}': {e!s}")


def _ensure_knowledge_source(section_key, cfg):
	source_name = cfg["source_name"]
	if frappe.db.exists("Knowledge Source", source_name):
		return
	try:
		frappe.get_doc({
			"doctype": "Knowledge Source",
			"source_name": source_name,
			"description": cfg["description"],
			# sqlite_fts requires no embedding-provider configuration, so the
			# bundled docs are searchable immediately on any site, with zero
			# setup. (Deviation from KNOWLEDGE_SKILL_PLAN.md, which specified
			# sqlite_hybrid — that requires an embedding_model/provider to be
			# configured before the source even validates, which would make
			# `after_migrate` seeding fail on a fresh site with no AI
			# Provider configured yet. sqlite_fts is Knowledge Source's own
			# documented zero-config fallback used elsewhere in this file,
			# e.g. huf.ai.app_seeding.loaders.upsert_knowledge's default.)
			"knowledge_type": "sqlite_fts",
			"scope": "Site",
		}).insert(ignore_permissions=True)
	except Exception as e:
		logger.warning(f"Failed to create Knowledge Source '{source_name}': {e!s}")


def _ensure_skill(section_key, cfg):
	skill_name = cfg["skill_name"]
	if frappe.db.exists("Skill", skill_name):
		return
	try:
		frappe.get_doc({
			"doctype": "Skill",
			"skill_name": skill_name,
			"title": cfg["title"],
			"skill_category": SKILL_CATEGORY_LABEL,
			"description": cfg["description"],
			"status": "Active",
			"source_type": "App Provided",
			"provider_app": "huf",
			# Opt-in, not on-by-default: this skill is never auto-loaded into
			# every agent's context, and this function never attaches it to
			# any Agent. A user opts an agent into it via Agent > Skills.
			"auto_load": 0,
			"instructions": cfg["instructions"],
			"skill_knowledge": [
				{
					"knowledge_source": cfg["source_name"],
					"mode": "Optional",
					"max_chunks": 6,
					"token_budget": 3000,
					"description": cfg["description"],
				}
			],
		}).insert(ignore_permissions=True)
	except Exception as e:
		logger.warning(f"Failed to create Skill '{skill_name}': {e!s}")


def _seed_knowledge_inputs_for_section(section_key, cfg):
	source_name = cfg["source_name"]
	if not frappe.db.exists("Knowledge Source", source_name):
		# Knowledge Source seeding failed or hasn't landed yet this pass;
		# skip content for this section rather than creating orphaned inputs.
		return 0

	section_dir = os.path.join(_data_dir(), section_key)
	if not os.path.isdir(section_dir):
		logger.warning(f"ERPNext docs section directory missing: {section_dir}")
		return 0

	existing_file_names = {
		row.file_name
		for row in frappe.get_all(
			"Knowledge Input",
			filters={"knowledge_source": source_name},
			fields=["file_name"],
		)
	}

	created = 0
	for fname in sorted(os.listdir(section_dir)):
		if not fname.endswith(".md") or fname == "INDEX.md":
			continue
		if fname in existing_file_names:
			continue

		fpath = os.path.join(section_dir, fname)
		try:
			with open(fpath, "r", encoding="utf-8") as f:
				text = f.read()
		except OSError as e:
			logger.warning(f"Failed to read {fpath}: {e!s}")
			continue

		if not text.strip():
			continue

		try:
			doc = frappe.get_doc({
				"doctype": "Knowledge Input",
				"knowledge_source": source_name,
				"input_type": "Text",
				"text": text,
			})
			doc.insert(ignore_permissions=True)
			# file_name isn't a Knowledge Input field for Text inputs (that
			# field is only populated for File inputs by before_save()), so
			# stamp it ourselves as the idempotency key for this loop.
			frappe.db.set_value("Knowledge Input", doc.name, "file_name", fname, update_modified=False)
			created += 1
		except frappe.DuplicateEntryError:
			# Same content hash already exists under this source (Knowledge
			# Input.check_duplicate) — nothing to do.
			continue
		except Exception as e:
			logger.warning(f"Failed to seed Knowledge Input for {source_name}/{fname}: {e!s}")
			continue

	return created


def seed_erpnext_knowledge():
	"""
	Idempotent entry point, wired to `after_migrate` in hooks.py.

	Ensures, per section (Setup/Data Model/Configurations/Buying/Selling/
	Stock/Website):
	  1. One Skill Category ("ERPNext Docs").
	  2. One Knowledge Source.
	  3. One opt-in (`auto_load: 0`) Skill linking to that Knowledge Source.
	  4. One Knowledge Input per bundled markdown file under that section,
	     which Knowledge Input's own after_insert hook chunks and indexes.
	Safe to call on every `bench migrate`.
	"""
	if not os.path.isdir(_data_dir()):
		logger.warning(f"ERPNext docs data directory not found, skipping seed: {_data_dir()}")
		return

	_ensure_skill_category()

	total_created = 0
	for section_key, cfg in SECTIONS.items():
		_ensure_knowledge_source(section_key, cfg)
		_ensure_skill(section_key, cfg)
		total_created += _seed_knowledge_inputs_for_section(section_key, cfg)

	if total_created:
		frappe.db.commit()
		logger.info(f"Seeded {total_created} new ERPNext docs Knowledge Input record(s)")
