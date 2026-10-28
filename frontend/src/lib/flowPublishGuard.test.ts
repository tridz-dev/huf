import { describe, expect, it } from 'vitest';
import type { FlowNode } from '@/types/flow.types';
import { publishBlockedReason, sensitiveFlowFeatures } from './flowPublishGuard';

const node = (data: Record<string, unknown>): FlowNode =>
  ({ id: 'n', type: 'x', position: { x: 0, y: 0 }, data: { label: 'n', nodeType: 'action', configured: true, ...data } }) as unknown as FlowNode;

const webhook = node({ triggerConfig: { type: 'webhook', method: 'POST', secret: 's' } });
const dataTrigger = node({ triggerConfig: { type: 'doc-event', doctype: 'ToDo', event: 'after_insert' } });
const httpStep = node({ actionConfig: { type: 'tool-call', tool_id: 'http_request' } });
const slackStep = node({ actionConfig: { type: 'tool-call', tool_id: 'slack_send_message' } });

describe('flowPublishGuard', () => {
  it('finds nothing in an ordinary flow', () => {
    expect(sensitiveFlowFeatures([webhook, slackStep])).toEqual([]);
    expect(publishBlockedReason([webhook, slackStep], false)).toBeNull();
  });

  it('names a Data trigger and a web request step once each', () => {
    expect(sensitiveFlowFeatures([dataTrigger, dataTrigger, httpStep])).toEqual(['a Data trigger', 'a web request step']);
  });

  it('blocks publishing for a user without the permission, with a plain reason', () => {
    const reason = publishBlockedReason([dataTrigger], false);
    expect(reason).toContain('a Data trigger');
    expect(reason).toContain('Ask an admin');
  });

  it('does not block a user who has the permission', () => {
    expect(publishBlockedReason([dataTrigger, httpStep], true)).toBeNull();
  });
});
