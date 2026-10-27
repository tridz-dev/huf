import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface SlackIdentityLink {
  name: string;
  gateway: string;
  team_id: string | null;
  external_id: string;
  user: string;
  state: string;
  source: string;
  display_label: string | null;
  linked_at: string | null;
  linked_by: string | null;
}

const IDENTITY = 'huf.ai.gateways.slack.identity';

export async function listSlackLinks(gatewayName: string): Promise<SlackIdentityLink[]> {
  try {
    const result = await call.get(`${IDENTITY}.list_identity_links`, { gateway: gatewayName });
    return (result?.message as SlackIdentityLink[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error loading linked people');
  }
}

export function buildSlackLinkParams(gatewayName: string, teamId: string, slackUserId: string, user: string) {
  return {
    gateway: gatewayName,
    team_id: teamId.trim().toUpperCase(),
    external_id: slackUserId.trim().toUpperCase(),
    user: user.trim(),
  };
}

export async function linkSlackUser(
  gatewayName: string,
  teamId: string,
  slackUserId: string,
  user: string
): Promise<void> {
  try {
    await call.post(`${IDENTITY}.link_identity`, buildSlackLinkParams(gatewayName, teamId, slackUserId, user));
  } catch (error) {
    handleFrappeError(error, 'Error linking the person');
  }
}

export async function unlinkSlackUser(name: string): Promise<void> {
  try {
    await call.post(`${IDENTITY}.unlink_identity`, { name });
  } catch (error) {
    handleFrappeError(error, 'Error removing the link');
  }
}
