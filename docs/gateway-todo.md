# Gateway Integration Status

The channel gateway foundation, adapters, and Agent tools for WhatsApp, Facebook Messenger, and Instagram Direct are fully implemented and integrated into `huf`.

## What is implemented and live

- **Backend DocTypes**: `Gateway`, `Gateway Binding`, `Gateway Access Entry`, `Gateway Event`.
- **Provider Adapters**:
  - `WhatsAppGatewayAdapter` (`huf.ai.gateway_adapters.whatsapp`): Meta WhatsApp Cloud API inbound verification, event normalization, and outbound delivery.
  - `MessengerGatewayAdapter` (`huf.ai.gateway_adapters.messenger`): Facebook Messenger page inbound verification, event normalization, and outbound delivery.
  - `InstagramGatewayAdapter` (`huf.ai.gateway_adapters.instagram`): Instagram Direct Professional account inbound verification, event normalization, and outbound delivery.
  - `VKGatewayAdapter`, `WeComGatewayAdapter`.
- **Agent Integration Tools**:
  - `whatsapp` tool (`huf.ai.tools.whatsapp`): Actions `send_message`, `send_template`, `list_messages`, `get_account_info`.
  - `messenger` tool (`huf.ai.tools.messenger`): Actions `send_message`, `list_conversations`, `list_messages`.
- **UI & Routing**:
  - `/gateways` route enabled in `App.tsx`.
  - Gateways navigation item enabled in `app-sidebar.tsx`.
  - `Gateway` trigger type enabled in `Flow Run`.
  - Gateway creation form in `GatewaysPage.tsx` supports WhatsApp, Messenger, Instagram, Telegram, Slack, and Email.
