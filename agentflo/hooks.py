app_name = "agentflo"
app_title = "AgentFlo"
app_publisher = "Tridz Technologies Pvt Ltd"
app_description = "AI Agent"
app_email = "info@tridz.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "agentflo",
# 		"logo": "/assets/agentflo/logo.png",
# 		"title": "AgentFlo",
# 		"route": "/agentflo",
# 		"has_permission": "agentflo.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/agentflo/css/agentflo.css"
# app_include_js = "/assets/agentflo/js/agentflo.js"

# include js, css files in header of web template
# web_include_css = "/assets/agentflo/css/agentflo.css"
# web_include_js = "/assets/agentflo/js/agentflo.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "agentflo/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "agentflo/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "agentflo.utils.jinja_methods",
# 	"filters": "agentflo.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "agentflo.install.before_install"
# after_install = "agentflo.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "agentflo.uninstall.before_uninstall"
# after_uninstall = "agentflo.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "agentflo.utils.before_app_install"
# after_app_install = "agentflo.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "agentflo.utils.before_app_uninstall"
# after_app_uninstall = "agentflo.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "agentflo.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "*": {
        "validate": "agentflo.ai.agent_hooks.run_hooked_agents",
        "before_insert": "agentflo.ai.agent_hooks.run_hooked_agents",
        "after_insert": "agentflo.ai.agent_hooks.run_hooked_agents",
        "before_save": "agentflo.ai.agent_hooks.run_hooked_agents",
        "after_save": "agentflo.ai.agent_hooks.run_hooked_agents",
        "before_submit": "agentflo.ai.agent_hooks.run_hooked_agents",
        "after_submit": "agentflo.ai.agent_hooks.run_hooked_agents",
        "before_cancel": "agentflo.ai.agent_hooks.run_hooked_agents",
        "on_submit": "agentflo.ai.agent_hooks.run_hooked_agents",
        "before_rename": "agentflo.ai.agent_hooks.run_hooked_agents",
        "after_rename": "agentflo.ai.agent_hooks.run_hooked_agents",
        "on_trash": "agentflo.ai.agent_hooks.run_hooked_agents",
        "after_delete": "agentflo.ai.agent_hooks.run_hooked_agents",
    }
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "all": [
        "agentflo.ai.agent_scheduler.run_scheduled_agents"
    ]
}

# Testing
# -------

# before_tests = "agentflo.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "agentflo.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "agentflo.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["agentflo.utils.before_request"]
# after_request = ["agentflo.utils.after_request"]

# Job Events
# ----------
# before_job = ["agentflo.utils.before_job"]
# after_job = ["agentflo.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"agentflo.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

