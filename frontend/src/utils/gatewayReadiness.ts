import type { GatewayDoc } from '@/services/gatewayApi';
import type { SlackSetupStatus } from '@/services/gateways/slackSetupApi';
import type { TeamsDiagnosis } from '@/services/gateways/teamsApi';

export type ReadinessItem = { id: string; label: string; done: boolean; hint?: string };
export type GatewayReadiness = { ready: boolean; items: ReadinessItem[]; blockingCount: number };

// Blocking items are the ones that must all be done for the gateway to actually work.
// "Receiving traffic" is informational only — a brand-new, correctly-configured gateway
// simply hasn't seen an event yet, so it must never hold up readiness.
const BLOCKING_ITEM_IDS = new Set(['credentials', 'route-target', 'enabled']);

export interface GatewayReadinessOptions {
  /** Cached Slack setup check result. Undefined means "not loaded / never checked". */
  slackSetup?: SlackSetupStatus | null;
  /** Latest Teams connection check. Undefined means "not loaded / never checked". */
  teamsDiagnosis?: TeamsDiagnosis | null;
}

function getSlackItems(status: SlackSetupStatus | null | undefined): ReadinessItem[] {
  const checked = Boolean(status && status.checked_at);
  const connectionDone = checked && Boolean(status?.checks.length) &&
    (status?.checks ?? []).filter((c) => !c.informational && c.id !== 'request_url').every((c) => c.ok);
  const urlDone = Boolean(status?.request_url_verified);
  return [
    {
      id: 'slack-connection',
      label: 'Slack connection verified',
      done: connectionDone,
      hint: checked ? 'Run the Slack check and fix what it lists' : 'Run the Slack check in the setup guide',
    },
    {
      id: 'slack-request-url',
      label: 'Slack confirmed the events address',
      done: urlDone,
      hint: 'In Slack, click Save Request URL under Event Subscriptions',
    },
  ];
}

function getTeamsItems(diagnosis: TeamsDiagnosis | null | undefined): ReadinessItem[] {
  const passed = (id: string) => diagnosis?.checks.find((c) => c.id === id)?.status === 'pass';
  return [
    {
      id: 'teams-credentials',
      label: 'App ID, secret and directory ID entered',
      done: passed('credentials_present'),
      hint: 'Enter the app ID, secret and directory (tenant) ID in the Credentials tab',
    },
    {
      id: 'teams-token',
      label: 'Microsoft accepted the sign-in',
      done: passed('token_acquisition'),
      hint: 'Run the Teams check in the setup guide and fix what it lists',
    },
    {
      id: 'teams-last-inbound',
      label: 'A Teams message reached Huf',
      done: passed('last_inbound'),
      hint: 'Say "help" to the bot in a personal chat in Teams',
    },
  ];
}

export function getGatewayReadiness(gateway: GatewayDoc, options: GatewayReadinessOptions = {}): GatewayReadiness {
  const items: ReadinessItem[] = [
    {
      id: 'credentials',
      label: 'Credentials connected',
      done: Boolean(gateway.integration_settings),
      hint: 'Connect credentials for this channel',
    },
    {
      id: 'route-target',
      label: 'Route target set',
      done: Boolean(gateway.default_target_type),
      hint: 'Choose an agent or flow to receive messages',
    },
    {
      id: 'enabled',
      label: 'Gateway enabled',
      done: Boolean(gateway.is_enabled),
      hint: 'Turn the gateway on',
    },
    {
      id: 'receiving-traffic',
      label: 'Receiving messages',
      done: Boolean(gateway.last_event_at),
      hint: 'No messages received yet',
    },
  ];

  // Slack items are blocking only once a check result exists; before that readiness is unknown,
  // so they are listed as not done without holding up the other providers' logic.
  const blockingIds = new Set(BLOCKING_ITEM_IDS);
  if (gateway.provider === 'Slack') {
    items.splice(3, 0, ...getSlackItems(options.slackSetup));
    if (options.slackSetup) {
      blockingIds.add('slack-connection');
      blockingIds.add('slack-request-url');
    }
  }

  if (gateway.provider === 'Microsoft Teams') {
    items.splice(3, 0, ...getTeamsItems(options.teamsDiagnosis));
    if (options.teamsDiagnosis) {
      blockingIds.add('teams-credentials');
      blockingIds.add('teams-token');
    }
  }

  if (gateway.last_error) {
    items.push({
      id: 'last-error',
      label: 'Last error',
      done: false,
      hint: gateway.last_error,
    });
  }

  const blockingCount = items.filter((item) => blockingIds.has(item.id) && !item.done).length;

  return {
    ready: blockingCount === 0,
    items,
    blockingCount,
  };
}
