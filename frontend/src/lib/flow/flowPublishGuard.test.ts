import { describe, expect, it } from 'vitest';
import type { FlowNode } from '@/types/flow.types';
import { publishBlockedReason, sensitiveFlowFeatures } from './flowPublishGuard';
import { codePublishBlockedReason } from '../flow-graph/codeFlow';

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

describe('Execute code publish check', () => {
  const codeStep = node({ actionConfig: { type: 'code-run', code: 'result = 1', profile: 'Flow Scratch' } });
  const status = (over: Record<string, unknown>) => ({ enabled: true, can_execute: true, ...over }) as never;

  it('only concerns flows with an Execute code step', () => {
    expect(codePublishBlockedReason([webhook], status({ enabled: false }))).toBeNull();
  });

  it('blocks when code is off or the user may not run code, never on an unknown status', () => {
    expect(codePublishBlockedReason([codeStep], status({ enabled: false }))).toBe('Execute code is turned off. An administrator can turn it on in Settings.');
    expect(codePublishBlockedReason([codeStep], status({ can_execute: false }))).toContain('Only people allowed to run code');
    expect(codePublishBlockedReason([codeStep], status({}))).toBeNull();
    expect(codePublishBlockedReason([codeStep], null)).toBeNull();
  });
});
