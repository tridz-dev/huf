import type { FlowNode } from '@/types/flow.types';

/** Capability needed to publish a flow that has a Data trigger or a web request step (mirrors the server rule). */
export const PUBLISH_SENSITIVE_CAPABILITY = 'flows.publish_sensitive';

const HTTP_TOOL_ID = 'http_request';

/** Plain names of what in the flow needs the publish permission (empty when nothing does). */
export function sensitiveFlowFeatures(nodes: FlowNode[]): string[] {
  const found: string[] = [];
  for (const node of nodes) {
    const data = node.data;
    if (data?.triggerConfig?.type === 'doc-event' && !found.includes('a Data trigger')) found.push('a Data trigger');
    const action = data?.actionConfig;
    if (action?.type === 'tool-call' && action.tool_id === HTTP_TOOL_ID && !found.includes('a web request step')) {
      found.push('a web request step');
    }
  }
  return found;
}

/** Why Publish is disabled for this user, or null when they may publish. */
export function publishBlockedReason(nodes: FlowNode[], canPublishSensitive: boolean): string | null {
  if (canPublishSensitive) return null;
  const features = sensitiveFlowFeatures(nodes);
  if (!features.length) return null;
  return `This flow has ${features.join(' and ')}. Only people allowed to publish flows that read data or send web requests can publish it. Ask an admin to publish it for you.`;
}
