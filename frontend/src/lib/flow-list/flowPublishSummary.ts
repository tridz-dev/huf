import { describeCron } from '@/lib/flow-trigger/scheduleText';
import { webhookUrl } from '@/lib/flow-graph/flowWebhookUi';
import { gatewayPhrase } from '@/lib/flow-gateway/gatewaySummary';
import { channelNoun, isGatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import { peekGatewayRegistry } from '@/lib/flow-gateway/registryStore';
import type { GatewayTriggerUiConfig, TriggerConfig } from '@/types/flow.types';

const DOC_EVENT_WORD: Record<string, string> = {
  after_insert: 'created',
  on_update: 'changed',
  on_submit: 'submitted',
  on_cancel: 'cancelled',
  on_trash: 'deleted',
};

export interface StartSummary {
  kind: 'webhook' | 'schedule' | 'doc-event' | 'chat' | 'none';
  /** Finishes "This flow will start ...": "when a request hits this address", "every day at 09:00". */
  text: string;
  /** The web address a webhook flow listens on (webhook only). */
  url?: string;
}

/** What will start the flow once it is live, in plain words. `origin` is the site address (window.location.origin). */
export function startSummary(trigger: TriggerConfig | undefined, flowId: string, origin: string): StartSummary {
  if (trigger && isGatewayKindId(trigger.type)) {
    const chat = trigger as GatewayTriggerUiConfig;
    if (!chat.gateway?.trim()) return { kind: 'none', text: `once you pick a ${channelNoun(trigger.type)}` };
    return { kind: 'chat', text: `when ${gatewayPhrase(trigger.type, chat, peekGatewayRegistry()?.gateways)}` };
  }
  switch (trigger?.type) {
    case 'webhook':
      return { kind: 'webhook', text: 'when a request hits this address', url: webhookUrl(origin, flowId) };
    case 'schedule': {
      const when = describeCron(trigger.cron).replace(/ \(server time\)$/, '');
      if (when.startsWith('No valid')) return { kind: 'none', text: 'once you choose a time' };
      const lower = when.charAt(0).toLowerCase() + when.slice(1);
      return { kind: 'schedule', text: lower.startsWith('custom schedule') ? 'on a custom schedule' : lower };
    }
    case 'doc-event': {
      const doctype = trigger.doctype?.trim();
      const event = trigger.event ? DOC_EVENT_WORD[trigger.event] : undefined;
      if (!doctype) return { kind: 'none', text: 'once you choose which records to watch' };
      return { kind: 'doc-event', text: `when a ${doctype} is ${event ?? 'changed'}` };
    }
    default:
      return { kind: 'none', text: 'once you choose what starts it' };
  }
}

/** Toast shown after publishing. */
export function publishedToast(start: StartSummary): { title: string; description: string } {
  const description =
    start.kind === 'none'
      ? 'It is live, but nothing starts it yet.'
      : `It will now start by itself ${start.text}. Unpublish to turn it off.`;
  return { title: 'Flow is live', description };
}
