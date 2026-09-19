/**
 * Single source of truth for the inbound webhook URL shown to admins for a
 * Gateway. Every provider is served by the generic gateway_webhook handler
 * except Slack, which verifies its own request-signing scheme and is routed
 * through slack_events.handle_slack_event instead (see huf/ai/gateways/slack_events.py).
 *
 * GW-17: this used to be duplicated between GatewaysPage.tsx (which forgot the
 * Slack special case) and ChannelTab.tsx (which had it right), so the two
 * gateway editors could show two different webhook URLs for the same Slack
 * gateway. Both surfaces must call this one function.
 */
export function getGatewayWebhookUrl(gatewayName: string, provider?: string, origin: string = window.location.origin): string {
  if (provider === 'Slack') {
    return `${origin}/api/method/huf.ai.gateways.slack_events.handle_slack_event?gateway_name=${encodeURIComponent(gatewayName)}`;
  }
  return `${origin}/api/method/huf.ai.gateway_webhook.handle_gateway_webhook?gateway_name=${encodeURIComponent(gatewayName)}`;
}
