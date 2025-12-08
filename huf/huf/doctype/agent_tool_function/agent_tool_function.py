# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _, is_whitelisted

from frappe.model.document import Document

import inspect 

import typing

import re

class AgentToolFunction(Document):
	def before_validate(self):
		self.validate_reference_doctype()
		self.validate_fields_for_doctype()
		self.prepare_function_params()
		self.validate_json()
		self.validate_tool_name()

	def validate_tool_name(self):
		if not re.match(r'^[a-zA-Z0-9_-]{1,128}$', self.tool_name or ""):
			frappe.throw(
				_("Tool name must contain only letters, numbers, underscore (_) or hyphen (-), no spaces, "
				"and be at most 128 characters long.")
			)


	def validate_reference_doctype(self):
		if not self.reference_doctype:
			if not self.types in [
				"Custom Function",
				"Send Message",
				"Get Report Result",
				"Run Agent",
				"Attach File to Document",
				"App Provided",
				"Speech to Text"
			]:
				frappe.throw(_("Please select a DocType for this function."))

	def validate_fields_for_doctype(self):
		if not self.reference_doctype:
			return

		doctype = frappe.get_meta(self.reference_doctype)

		for param in self.parameters:

			if param.child_table_name:
				child_table = doctype.get_field(param.child_table_name)
				if not child_table:
					frappe.throw(
						_("Child table {0} not found in {1}").format(param.child_table_name, self.reference_doctype)
					)


				child_meta = frappe.get_meta(child_table.options)
				if not child_meta:
					frappe.throw(_("Child table {0} is not a valid doctype").format(param.child_table_name))


				docfield = child_meta.get_field(param.fieldname)
				if not docfield:
					frappe.throw(_("Field {0} not found in {1}").format(param.fieldname, child_table.options))
			else:

				field = doctype.get_field(param.fieldname)

				if not field:
					frappe.throw(_("Field {0} not found in {1}").format(param.fieldname, self.reference_doctype))

				if field.fieldtype == "Select":
					if not param.options:
						frappe.throw(_("Options are required for select fields"))

					select_options = field.options.split("\n")
					for option in param.options.split("\n"):
						if option not in select_options:
							frappe.throw(
								_("Option {0} is not valid for field {1} in {2}").format(
									option, param.fieldname, self.reference_doctype
								)
							)

	def prepare_function_params(self):
		"""
		Set the function params based on the type of function and other inputs
		"""
		params = {}
		if self.types == "Get Document":
			properties = {
				"document_id": {
					"type": "string",
					"description": f"The ID of the {self.reference_doctype} to get (optional)"
				}
			}

			for param in self.parameters:
				properties[param.fieldname] = {
					"type": param.type,
					"description": param.label,
				}

			params = {
				"type": "object",
				"properties": properties,
				"required": [],
				"additionalProperties": False,
			}

		elif self.types == "Get Multiple Documents":
			params = {
				"type": "object",
				"properties": {
					"document_ids": {
						"type": "array",
						"items": {"type": "string"},
						"description": f"The IDs of the {self.reference_doctype}s to get",
					}
				},
				"required": ["document_ids"],
				"additionalProperties": False,
			}

		elif self.types == "Delete Document":
			params = {
				"type": "object",
				"properties": {
					"document_id": {
						"type": "string",
						"description": f"The ID of the {self.reference_doctype} to delete",
					}
				},
				"required": ["document_id"],
				"additionalProperties": False,
			}

		elif self.types == "Delete Multiple Documents":
			params = {
				"type": "object",
				"properties": {
					"document_ids": {
						"type": "array",
						"items": {"type": "string"},
						"description": f"The IDs of the {self.reference_doctype}s to delete",
					}
				},
				"required": ["document_ids"],
				"additionalProperties": False,
			}
		elif self.types == "Submit Document":
			params = {
				"type": "object",
				"properties": {
					"document_id": {
						"type": "string",
						"description": f"The ID of the {self.reference_doctype} to submit",
					}
				},
				"required": ["document_id"],
				"additionalProperties": False,
			}
		elif self.types == "Cancel Document":
			params = {
				"type": "object",
				"properties": {
					"document_id": {
						"type": "string",
						"description": f"The ID of the {self.reference_doctype} to cancel",
					}
				},
				"required": ["document_id"],
				"additionalProperties": False,
			}
		elif self.types == "Get Amended Document":
			params = {
				"type": "object",
				"properties": {
					"document_id": {
						"type": "string",
						"description": f"The ID of the {self.reference_doctype} to get the amended document for",
					}
				},
				"required": ["document_id"],
				"additionalProperties": False,
			}

		elif self.types == "Attach File to Document":
			params = {
				"type": "object",
				"properties": {
					"reference_doctype": {
						"type": "string",
						"description": "The DocType of the document to attach the file to (e.g. Lead, Customer).",
					},
					"document_id": {
						"type": "string",
						"description": "The ID (name) of the document to attach the file to (e.g. CRM-LEAD-2025-00016).",
					},
					"file_url": {
						"type": "string",
						"description": "The URL/path of an existing file (e.g. /files/Sanju.jpg)."
					},
					"file_id": {
						"type": "string",
						"description": "The File document name if already uploaded (optional)."
					}
				},
				"required": ["reference_doctype", "document_id"],
				"additionalProperties": False,
			}

		elif self.types == "Custom Function":
			if self.pass_parameters_as_json:
				params = self.build_params_json_from_table()
			else:
				params = self.get_params_as_dict()
		elif self.types == "Get List":
			
			filter_properties = {}
			for param in self.parameters:
				filter_properties[param.fieldname] = {
					"type": param.type,
					"description": param.label or f"Filter by {param.fieldname}"
				}

			params = {
				"type": "object",
				"properties": {
					"filters": {
						"type": "object",
						"description": "Dictionary of filters. Example: {'status': 'New', 'first_name': 'John Doe'}.",
						"properties": filter_properties, 
						"additionalProperties": True 
					},
					"fields": {
						"type": "array",
						"items": {"type": "string"},
						"description": "List of fields to retrieve.",
					},
					"limit": {
						"type": "integer",
						"description": "Max records to return. Set to 0 to fetch ALL records.",
						"default": 0,
					},
				},
				"additionalProperties": False,
			}
			params["required"] = []

		elif self.types == "Get Value":
			params = {
				"type": "object",
				"properties": {
					"doctype": {
						"type": "string",
						"description": "The DocType to get the value from",
					},
					"filters": {
						"type": "object",
						"description": "Filters to apply when retrieving the value",
					},
					"fieldname": {
						"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
						"description": "The fields whose value needs to be returned. Can be a single field or a list of fields. If a list of fields is provided, the values will be returned as a tuple.",
					},
				},
				"required": ["doctype", "filters", "fieldname"],
				"additionalProperties": False,
			}
		elif self.types == "Set Value":
			params = {
				"type": "object",
				"properties": {
					"doctype": {
						"type": "string",
						"description": "The DocType to set the value for",
					},
					"document_id": {
						"type": "string",
						"description": "The ID of the document to set the value for",
					},
					"fieldname": {
						"anyOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}],
						"description": "The fields whose value needs to be set. Can be a single field or a JSON object with key value pairs.",
					},
					"value": {
						"type": "string",
						"description": "The value to set for the field. This is required if fieldname is a string.",
					},
				},
				"required": ["doctype", "document_id", "fieldname"],
				"additionalProperties": False,
			}
		elif self.types == "Get Report Result":
			params = {
				"type": "object",
				"properties": {
					"report_name": {"type": "string", "description": "Report Name"},
					"filters": {
						"type": "object",
						"properties": {
							"company": {"type": "string", "description": "Company name to run the report for"},
							"from_date": {"type": "string", "description": "generate report from this date"},
							"to_date": {"type": "string", "description": "generate report till this date"},
						},
						"required": ["company", "to_date", "from_date"],
					},
					"limit": {"type": "number", "description": "Limit for the number of records to be fetched"},
					"ignore_prepared_report": {
						"type": "boolean",
						"description": "Whether to ignore the prepared report",
					},
					"user": {"type": "string", "description": "The user to run the report for"},
					"are_default_filters": {
						"type": "boolean",
						"description": "Whether to use the default filters",
					},
				},
				"required": ["report_name"],
			}

		elif self.types == "GET":

			query_properties = {}
			query_required = []

			for param in self.parameters:
				field_schema = {"type": param.type, "description": param.label}
				if param.type == "string" and param.options:
					field_schema["enum"] = param.options.split("\n")

				query_properties[param.fieldname] = field_schema
				if param.required:
					query_required.append(param.fieldname)

			params = {
				"type": "object",
				"properties": {
					"url": {
						"type": "string",
						"description": f"The URL to send the GET request to. Base URL: {self.base_url or 'Not set'}"
					},
					"params": {
						"type": "object",
						"properties": query_properties,
						"required": query_required,
						"additionalProperties": False
					}
				},
				"required": ["url", "params"] if query_required else ["url"],
				"additionalProperties": False,
			}


		elif self.types == "POST":

			body_properties = {}
			body_required = []

			for param in self.parameters:
				field_schema = {"type": param.type, "description": param.label}

				if param.type == "string" and param.options:
					field_schema["enum"] = param.options.split("\n")

				body_properties[param.fieldname] = field_schema
				if param.required:
					body_required.append(param.fieldname)

			params = {
				"type": "object",
				"properties": {
					"url": {
						"type": "string",
						"description": f"The URL to send the POST request to. Base URL: {self.base_url or 'Not set'}"
					},
					"json_data": {
						"type": "object",
						"properties": body_properties,
						"required": body_required,
						"additionalProperties": False,
					}
				},
				"required": ["url", "json_data"],
				"additionalProperties": False,
			}
		elif self.types == "Speech to Text":
			params = {
				"type": "object",
				"properties": {
					"file_id": {
						"type": "string",
						"description": "Existing File document ID (optional). If provided, file_url not required."
					},
					"file_url": {
						"type": "string",
						"description": "Path/URL of audio file (optional). Example: /files/my-audio.mp3"
					},
					"language": {
						"type": "string",
						"description": "Optional language code (e.g. en, ml). If omitted, auto-detect is used."
					},
					"translate": {
						"type": "boolean",
						"description": "If true, translate audio to English (if model supports).",
						"default": False
					},
					"model": {
						"type": "string",
						"description": "Speech model to use (default: whisper-1)",
						"default": "whisper-1"
					},
					"provider": {
						"type": "string",
						"description": "Optional AI Provider name from 'AI Provider' doctype (used to get API key)."
					},
					"api_key": {
						"type": "string",
						"description": "Optional API key override (leave empty to use AI Provider)."
					}
				},
				"required": [],
				"additionalProperties": False
			}
					
		else:
			params = self.build_params_json_from_table()

		self.params = json.dumps(params, indent=4)

	def build_params_json_from_table(self):
		params = {
			"type": "object",
			"additionalProperties": False,
		}

		required = []
		properties = {}

		child_tables = {}

		if self.types == "Update Document" or self.types == "Update Multiple Documents":
			properties["document_id"] = {
				"type": "string",
				"description": f"The ID of the {self.reference_doctype} to update",
			}
			required.append("document_id")

		for param in self.parameters:
			obj = {
				"type": param.type,
				"description": param.label,
			}

			if param.type == "string" and param.options:
				obj["enum"] = param.options.split("\n")

			if not param.child_table_name:
				properties[param.fieldname] = obj

				if param.required:
					required.append(param.fieldname)
			else:
				if param.child_table_name not in child_tables:
					child_tables[param.child_table_name] = {
						"type": "array",
						"items": {
							"type": "object",
							"additionalProperties": False,
							"properties": {param.fieldname: obj},
							"required": [],
						},
					}
				else:
					child_tables[param.child_table_name]["items"]["properties"][param.fieldname] = obj

				if param.required:
					child_tables[param.child_table_name]["items"]["required"].append(param.fieldname)

		for child_table_name, child_table in child_tables.items():
		
			if self.reference_doctype:
				try:
					doctype_meta = frappe.get_meta(self.reference_doctype)
					table_field = doctype_meta.get_field(child_table_name)
				except Exception:
					pass 
			
			properties[child_table_name] = child_table

		if self.types == "Create Multiple Documents" or self.types == "Update Multiple Documents":
			params["properties"] = {
				"data": {
					"type": "array",
					"items": {
						"type": "object",
						"properties": properties,
						"required": required,
						"additionalProperties": False,
					},
				}
			}
			
		else:
			params["properties"] = properties
			params["required"] = required

		return params

	def validate_json(self):
		if self.types == "Custom Function":
			if not self.function_path:
				frappe.throw(_("Function path is required for Custom Functions"))


			try:
				json.loads(self.params)
			except json.JSONDecodeError:
				frappe.throw(_("Invalid JSON in params"))

			self.params = json.dumps(json.loads(self.params), indent=4)

	def validate(self):

		INVALID_FUNCTION_NAMES = [
			"get_document",
			"get_documents",
			"get_list",
			"create_document",
			"create_documents",
			"update_document",
			"update_documents",
			"delete_document",
			"delete_documents",
		]
		if self.tool_name in INVALID_FUNCTION_NAMES:
			frappe.throw(
				_("Function name cannot be one of the core functions. Please choose a different name.")
			)

		DOCUMENT_REF_FUNCTIONS = [
			"Get Document",
			"Get Multiple Documents",
			"Get List",
			"Create Document",
			"Create Multiple Documents",
			"Update Document",
			"Update Multiple Documents",
			"Delete Document",
			"Delete Multiple Documents",
			"Submit Document",
			"Cancel Document",
			"Get Amended Document",
		]
		if self.types in DOCUMENT_REF_FUNCTIONS:
			if not self.reference_doctype:
				frappe.throw(_("Please select a DocType for this function."))


		if self.types == "Custom Function":
			f = frappe.get_attr(self.function_path)
			if not f:
				frappe.throw(_("Function not found"))

			is_whitelisted(f)

	def before_save(self):

		params = self.get_params_as_dict()

		function_definition = {
			"name": self.tool_name,
			"description": self.description,
			"parameters": params,
		}

		self.function_definition = json.dumps(function_definition, indent=4)

	def on_update(self):


		agents = frappe.get_all("Agent Tool", filters={"tool": self.name}, pluck="parent")

		for agents in agents:
			agent = frappe.get_doc("Agent", agents)

	def get_params_as_dict(self):
		if isinstance(self.params, dict):
			return self.params
		if isinstance(self.params, str):
			return json.loads(self.params)
		return {}

	@frappe.whitelist()
	def fetch_parameters_from_code(self):
		"""
		Inspects the function at function_path and populates the parameters table.
		"""
		if not self.function_path:
			frappe.throw(_("Please provide a Function Path first."))

		try:
			func = frappe.get_attr(self.function_path)
		except Exception as e:
			frappe.throw(_("Could not find function at {0}: {1}").format(self.function_path, str(e)))

		sig = inspect.signature(func)
		self.set("parameters", [])

		for name, param in sig.parameters.items():
			if name in ["self", "cls"]:
				continue
			
			param_type = "string"
			if param.annotation != inspect.Parameter.empty:
				if param.annotation == int:
					param_type = "integer"
				elif param.annotation == bool:
					param_type = "boolean"
				elif param.annotation == float:
					param_type = "number"
				elif param.annotation == dict or param.annotation == typing.Dict:
					param_type = "object"
				elif param.annotation == list or param.annotation == typing.List:
					param_type = "array"
			
			reqd = 1
			if param.default != inspect.Parameter.empty:
				reqd = 0

			self.append("parameters", {
				"fieldname": name,
				"label": name.replace("_", " ").title(),
				"type": param_type,
				"required": reqd,
			})
		self.pass_parameters_as_json = 1
		self.save()
		return _("Parameters fetched successfully.")