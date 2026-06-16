from huf.ai.app_installer import install_huf_app as _install

HUF_APP_TOOLS = [
    {
        "name": "install_huf_app",
        "description": (
            "Install a Huf App from a JSON manifest. Call this when the user has confirmed "
            "the app design and wants to build it. Returns the installed app_id and agent name."
        ),
        "function": _install,
        "parameters": {
            "manifest": {
                "type": "string",
                "description": "The full app manifest as a JSON string matching the Huf App manifest schema.",
                "required": True,
            }
        },
    }
]
