app_name = "huf"
app_title = "Huf"
app_publisher = "Tridz Technologies Pvt Ltd"
app_description = "Build and run smart AI agents with tools, chat, and automation directly in the Frappe ecosystem."
app_email = "info@tridz.com"
app_license = "agpl"
source_link = "https://github.com/tridz-dev/huf.git"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "huf",
        "logo": "/assets/huf/Images/Huf.jpg",
		"title": "Huf",
		"route": "huf",
		"has_permission": "huf.permission.check_app_permission"
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/huf/css/huf.css"
# app_include_js = "/assets/huf/js/huf.js"

# include js, css files in header of web template
# web_include_css = "/assets/huf/css/huf.css"
# web_include_js = "/assets/huf/js/huf.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "huf/public/scss/website"

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
# app_include_icons = "huf/public/icons.svg"

# Home Pages
# ----------
website_route_rules = [
    # Docs routes must come before the catch-all /huf route
    {"from_route": "/huf/docs", "to_route": "huf/docs"},
    {
        "from_route": "/huf/docs/<path:app_path>", 
        "to_route": "huf/docs/<path:app_path>"
    },
    {"from_route": "/huf/<path:app_path>", "to_route": "huf"},
    {"from_route": "/huf/stream", "to_route": "huf/stream"}
]

# Register custom page renderer for SSE streaming and docs
page_renderer = [
    "huf.ai.agent_stream_renderer.AgentStreamRenderer",
    "huf.www.docs_renderer.DocsRenderer",
]


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
# 	"methods": "huf.utils.jinja_methods",
# 	"filters": "huf.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "huf.install.before_install"
after_install = "huf.install.after_install"
after_migrate = "huf.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "huf.uninstall.before_uninstall"
after_uninstall = "huf.ai.tool_registry.sync_app_tools"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "huf.utils.before_app_install"
# after_app_install = "huf.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "huf.utils.before_app_uninstall"
# after_app_uninstall = "huf.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "huf.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
permission_query_conditions = {
    "Agent": "huf.huf.doctype.agent.agent.get_permission_query_conditions",
}
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
        "validate": "huf.ai.agent_hooks.run_hooked_agents",
        "before_insert": "huf.ai.agent_hooks.run_hooked_agents",
        "after_insert": "huf.ai.agent_hooks.run_hooked_agents",
        "before_save": "huf.ai.agent_hooks.run_hooked_agents",
        "after_save": "huf.ai.agent_hooks.run_hooked_agents",
        "before_submit": "huf.ai.agent_hooks.run_hooked_agents",
        "after_submit": "huf.ai.agent_hooks.run_hooked_agents",
        "before_cancel": "huf.ai.agent_hooks.run_hooked_agents",
        "on_submit": "huf.ai.agent_hooks.run_hooked_agents",
        "on_update": "huf.ai.agent_hooks.run_hooked_agents",
        "before_rename": "huf.ai.agent_hooks.run_hooked_agents",
        "after_rename": "huf.ai.agent_hooks.run_hooked_agents",
        "on_trash": "huf.ai.agent_hooks.run_hooked_agents",
        "after_delete": "huf.ai.agent_hooks.run_hooked_agents",
    },
    "Agent Trigger": {
        "after_insert": "huf.ai.agent_hooks.clear_doc_event_agents_cache",
        "on_update": "huf.ai.agent_hooks.clear_doc_event_agents_cache",
        "on_trash": "huf.ai.agent_hooks.clear_doc_event_agents_cache",
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"huf.tasks.all"
# 	],
# 	"daily": [
# 		"huf.tasks.daily"
# 	],
# 	"hourly": [
# 		"huf.tasks.hourly"
# 	],
# 	"weekly": [
# 		"huf.tasks.weekly"
# 	],
# 	"monthly": [
# 		"huf.tasks.monthly"
# 	],
# }
scheduler_events = {
    "all": [
        "huf.ai.agent_scheduler.run_scheduled_agents"
    ],
    "cron": {
        "*/1 * * * *": [
            "huf.ai.orchestration.scheduler.process_orchestrations"
        ]
    }
}


# Testing
# -------

# before_tests = "huf.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "huf.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "huf.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["huf.utils.before_request"]
# after_request = ["huf.utils.after_request"]

# Job Events
# ----------
# before_job = ["huf.utils.before_job"]
# after_job = ["huf.utils.after_job"]

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
# 	"huf.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
fixtures = [
    {
        "dt": "Custom HTML Block",
        "filters": [
            ["name", "=", "Huf"]
        ]
    }
]
