"""Migration patch: resync Integration Service.required_credentials with each
provider's actual validation requirements (GW-13, GW-14).

install.py's hand-maintained `register_integration_services()` seed had drifted
from what Gateway.validate() / the gateway adapters actually require:

- Slack: `signing_secret` was missing entirely from required_credentials, even
  though Gateway._validate_slack_signing_secret() hard-requires it for every
  enabled Slack gateway (GW-13).
- Telegram: `webhook_secret` was missing entirely, even though
  TelegramGatewayAdapter.credential_schema marks it required (GW-14).
- WhatsApp/Messenger/Instagram: `app_secret` was seeded with required=False,
  even though each adapter's credential_schema marks it required (GW-14).
- Email: `webhook_secret` was seeded with required=False, even though
  EmailGatewayAdapter.credential_schema marks it required (GW-14).
- Google Chat: `verification_token` was seeded with required=False, even
  though GoogleChatGatewayAdapter.credential_schema marks it required (GW-14).

install.py's `register_integration_services()` now derives required_credentials
directly from each adapter's credential_schema (the single source of truth), so
re-running it here brings already-installed sites' Integration Service records
in line with what a fresh install would produce.
"""

from huf.install import register_integration_services


def execute():
	register_integration_services()
