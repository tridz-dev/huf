# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Meta Embedded Signup for WhatsApp (Huf as Tech Provider).

Three modes (``Channel Embedded Signup Settings.mode``):

* ``direct``: this site owns the Facebook app; the code from the FB JS SDK is exchanged here.
* ``broker``: a central Huf Cloud broker owns the app; this site posts the code to it and gets
  the business token back.
* ``broker_server``: this site IS the broker; it exposes :func:`broker_exchange` to tenants.

The business token is written to the Integration Settings credential store (Password field) and
never returned, logged or placed in an Error Log. All Graph calls use ``requests`` with timeouts.

Layout: ``core`` (constants, helpers, settings API), ``tenant`` (code exchange, ``complete_signup``),
``broker`` (``broker_server`` endpoints and the webhook fan-out). Everything is re-exported here so the
dotted whitelisted paths (``huf.ai.channels.embedded_signup.<fn>``) stay stable.
"""

from huf.ai.channels.embedded_signup.broker import (  # noqa: F401
	_callback_ok,
	_record_waba,
	broker_exchange,
	broker_webhook,
	forward_to_tenant,
)
from huf.ai.channels.embedded_signup.core import (  # noqa: F401
	SETTINGS,
	WABA_DOCTYPE,
	create_tenant_key,
	get_settings_admin,
	get_signup_config,
	hash_api_key,
	require_https_url,
	save_settings,
)
from huf.ai.channels.embedded_signup.tenant import complete_signup  # noqa: F401
