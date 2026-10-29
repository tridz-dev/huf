import { describe, it, expect } from 'vitest';
import { actionHasConfiguredContent } from './flowNodeConfigured';
import type { ActionConfig } from '../../types/flow.types';

const check = (actionConfig: ActionConfig | undefined, configured = true) =>
  actionHasConfiguredContent({ actionConfig, configured });

describe('actionHasConfiguredContent', () => {
  it('is false for a freshly picked action type with no fields filled', () => {
    // NodeSelectionModal sets configured: true as soon as the type is picked.
    expect(check({ type: 'agent-run' }, true)).toBe(false);
    expect(check({ type: 'tool-call', tool_id: '   ' }, true)).toBe(false);
  });

  it('is true once a meaningful field has content', () => {
    expect(check({ type: 'agent-run', agent: 'support' })).toBe(true);
    expect(check({ type: 'tool-call', tool_id: 'search' })).toBe(true);
    expect(check({ type: 'foreach', items: { $from: 'input.items' } })).toBe(true);
  });

  it('treats a condition expression as configuration', () => {
    expect(check({ type: 'condition', expression: "input['a'] > 1" })).toBe(true);
    expect(check({ type: 'condition' })).toBe(false);
  });

  it('treats approval assignees as configuration', () => {
    expect(check({ type: 'human.approval', approver_users: ['a@b.c'] })).toBe(true);
    expect(check({ type: 'human.approval', approver_users: [] })).toBe(false);
  });

  it('treats a chosen transform op as configuration', () => {
    expect(check({ type: 'transform', op: 'lower', input: {} })).toBe(true);
    expect(check({ type: 'transform', input: {} })).toBe(false);
  });

  it('treats new node fields as configuration', () => {
    expect(check({ type: 'state-get', key: 'cart' })).toBe(true);
    expect(check({ type: 'state-set', key: '' })).toBe(false);
    expect(check({ type: 'doc-create', doctype: 'ToDo', fields: {} })).toBe(true);
    expect(check({ type: 'doc-create', doctype: ' ' })).toBe(false);
  });

  it('is false when there is no action config at all', () => {
    expect(check(undefined, true)).toBe(false);
  });
});
