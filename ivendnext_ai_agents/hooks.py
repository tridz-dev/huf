app_name = "ivendnext_ai_agents"
app_title = "Ivendnext Ai Agents"
app_publisher = "Tridz Technologies Pvt Ltd"
app_description = "Build and run smart AI agents with tools, chat, and automation directly in the Frappe ecosystem."
app_email = "info@tridz.com"
app_license = "agpl"
source_link = "https://github.com/tridz-dev/huf.git"
app_logo_url="/assets/ivendnext_ai_agents/Images/huf.png"
# for version 16+ this has to be /desk/huf, this is being updated in after_app_install hook
app_url="ivendnext_ai_agents"
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "ivendnext_ai_agents",
		"logo": app_logo_url,
		"title": "Ivendnext Ai Agents",
		"route": app_url,
		"has_permission": "ivendnext_ai_agents.permission.check_app_permission"
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/ivendnext_ai_agents/css/huf.css"
# app_include_js = "/assets/ivendnext_ai_agents/js/huf.js"

# include js, css files in header of web template
# web_include_css = "/assets/ivendnext_ai_agents/css/huf.css"
# web_include_js = "/assets/ivendnext_ai_agents/js/huf.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ivendnext_ai_agents/public/scss/website"

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
# app_include_icons = "ivendnext_ai_agents/public/icons.svg"

# Home Pages
# ----------
website_route_rules = [
    {"from_route": "/ivendnext_ai_agents/stream/ping", "to_route": "ivendnext_ai_agents/stream/ping"},
    {"from_route": "/ivendnext_ai_agents/stream/<path:agent_name>", "to_route": "ivendnext_ai_agents/stream"},
    {"from_route": "/ivendnext_ai_agents/stream", "to_route": "ivendnext_ai_agents/stream"},

    # Docs routes must come before the catch-all /huf route
    {"from_route": "/ivendnext_ai_agents/docs", "to_route": "ivendnext_ai_agents/docs"},
    {
        "from_route": "/ivendnext_ai_agents/docs/<path:app_path>", 
        "to_route": "ivendnext_ai_agents/docs/<path:app_path>"
    },
    {"from_route": "/ivendnext_ai_agents/<path:app_path>", "to_route": "ivendnext_ai_agents"},
]

# Register custom page renderer for SSE streaming and docs
page_renderer = [
    "ivendnext_ai_agents.ai.agent_stream_renderer.AgentStreamRenderer",
    "ivendnext_ai_agents.www.docs_renderer.DocsRenderer",
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
# 	"methods": "ivendnext_ai_agents.utils.jinja_methods",
# 	"filters": "ivendnext_ai_agents.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "ivendnext_ai_agents.install.before_install"
after_install = "ivendnext_ai_agents.install.after_install"
after_app_install = "ivendnext_ai_agents.install.setup_desktop_icon_as_workspace"
after_migrate = "ivendnext_ai_agents.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "ivendnext_ai_agents.uninstall.before_uninstall"
after_uninstall = "ivendnext_ai_agents.ai.tool_registry.sync_app_tools"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ivendnext_ai_agents.utils.before_app_install"
# after_app_install = "ivendnext_ai_agents.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ivendnext_ai_agents.utils.before_app_uninstall"
# after_app_uninstall = "ivendnext_ai_agents.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ivendnext_ai_agents.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
permission_query_conditions = {
    "Agent": "ivendnext_ai_agents.ivendnext_ai_agents.doctype.agent.agent.get_permission_query_conditions",
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
        "validate": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "before_insert": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "after_insert": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "before_save": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "after_save": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "before_submit": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "after_submit": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "before_cancel": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "on_submit": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "on_update": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "before_rename": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "after_rename": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "on_trash": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
        "after_delete": "ivendnext_ai_agents.ai.agent_hooks.run_hooked_agents",
    },
    "Agent Trigger": {
        "after_insert": "ivendnext_ai_agents.ai.agent_hooks.clear_doc_event_agents_cache",
        "on_update": "ivendnext_ai_agents.ai.agent_hooks.clear_doc_event_agents_cache",
        "on_trash": "ivendnext_ai_agents.ai.agent_hooks.clear_doc_event_agents_cache",
    },
    "Knowledge Source": {
        "after_insert": "ivendnext_ai_agents.ai.knowledge.hooks.on_knowledge_source_created",
        "on_update": "ivendnext_ai_agents.ai.knowledge.hooks.on_knowledge_source_updated",
        "on_trash": "ivendnext_ai_agents.ai.knowledge.hooks.on_knowledge_source_deleted",
    },
    "Knowledge Input": {
        "on_trash": "ivendnext_ai_agents.ai.knowledge.hooks.on_knowledge_input_deleted",
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"ivendnext_ai_agents.tasks.all"
# 	],
# 	"daily": [
# 		"ivendnext_ai_agents.tasks.daily"
# 	],
# 	"hourly": [
# 		"ivendnext_ai_agents.tasks.hourly"
# 	],
# 	"weekly": [
# 		"ivendnext_ai_agents.tasks.weekly"
# 	],
# 	"monthly": [
# 		"ivendnext_ai_agents.tasks.monthly"
# 	],
# }
scheduler_events = {
    "all": [
        "ivendnext_ai_agents.ai.agent_scheduler.run_scheduled_agents"
    ],
    "daily": [
        "ivendnext_ai_agents.ai.knowledge.maintenance.cleanup_orphaned_files",
        "ivendnext_ai_agents.ai.knowledge.maintenance.optimize_indexes",
    ],
    "cron": {
        "*/1 * * * *": [
            "ivendnext_ai_agents.ai.orchestration.scheduler.process_orchestrations"
        ]
    },
    "hourly": [
        "ivendnext_ai_agents.ai.mcp_client.auto_sync_mcp_server_tools"
    ]
}


# Testing
# -------

# before_tests = "ivendnext_ai_agents.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ivendnext_ai_agents.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "ivendnext_ai_agents.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["ivendnext_ai_agents.utils.before_request"]
# after_request = ["ivendnext_ai_agents.utils.after_request"]

# Job Events
# ----------
# before_job = ["ivendnext_ai_agents.utils.before_job"]
# after_job = ["ivendnext_ai_agents.utils.after_job"]

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
# 	"ivendnext_ai_agents.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
# Flow Engine Tools
# -----------------
# Register flow tools so agents can interact with flows

fixtures = [
    {
        "dt": "Custom HTML Block",
        "filters": [
            ["name", "=", "Ivendnext Ai Agents"]
        ]
    }
]