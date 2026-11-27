import { afterEach, describe, expect, it } from 'vitest';
import { actionOptions } from '@/data/actions';
import { triggerOptions } from '@/data/triggers';
import { missingAppStep, setAppNodeTypes } from '@/lib/flow-graph/appNodeTypes';
import { addActionStep } from '@/lib/flow-graph/flowCanvasGraph';
import { deserializeFlow, serializeFlow } from '@/services/flowSerializer';
import { readEmbedApp, setEmbedApp, setScopeTypes } from './embedScope';
import { isActionAllowed, isStepAllowed, isTriggerAllowed } from './scopeFilter';

const SCOPE = ['happiol.grant_points', 'trigger.schedule', 'trigger.doc-event', 'condition', 'output'];
const scoped = () => {
  setEmbedApp('happiol');
  setScopeTypes(SCOPE);
};

afterEach(() => {
  setEmbedApp(null);
  setAppNodeTypes(null);
});

describe('readEmbedApp', () => {
  it('scopes only the embed route, and a bad app fails closed', () => {
    expect(readEmbedApp({ pathname: '/huf/flows/a', search: '?app=happiol' })).toBeNull();
    expect(readEmbedApp({ pathname: '/huf/embed/flow/a', search: '?app=happiol' })).toBe('happiol');
    expect(readEmbedApp({ pathname: '/huf/embed/flow/a', search: '' })).toBe('');
    expect(readEmbedApp({ pathname: '/huf/embed/flow/a', search: '?app=../x' })).toBe('');
  });
});

describe('palette filtering', () => {
  it('offers everything outside embed mode', () => {
    expect(actionOptions.every((a) => isActionAllowed(a.id))).toBe(true);
    expect(triggerOptions.every((t) => isTriggerAllowed(t.id))).toBe(true);
  });

  it('offers only scoped types', () => {
    scoped();
    expect(actionOptions.filter((a) => isActionAllowed(a.id)).map((a) => a.id)).toEqual(['condition', 'end']);
    expect(isActionAllowed('happiol.grant_points')).toBe(true);
    expect(isActionAllowed('other.step')).toBe(false);
    expect(triggerOptions.filter((t) => isTriggerAllowed(t.id)).map((t) => t.id)).toEqual(['schedule', 'doc-event']);
  });

  it('offers nothing before the list arrives', () => {
    setEmbedApp('happiol');
    expect(actionOptions.some((a) => isActionAllowed(a.id))).toBe(false);
  });

  it('refuses to add an out-of-scope step', () => {
    scoped();
    const trigger = { id: 't', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'T', nodeType: 'trigger' as const } } as never;
    expect(addActionStep([trigger], [], 't', 'next', 'code-run', { type: 'code-run' } as never)).toBeNull();
    expect(addActionStep([trigger], [], 't', 'next', 'condition', { type: 'condition' } as never)).not.toBeNull();
  });
});

describe('existing out-of-scope steps', () => {
  const definition = {
    nodes: [
      { id: 'a', type: 'tool.call', config: { tool_id: 'http_request', input: { url: 'x' } } },
      { id: 'b', type: 'other.step', config: { text: 'hi' } },
    ],
  };

  it('are read-only, are not reported as uninstalled, and survive a save unchanged', () => {
    scoped();
    setAppNodeTypes([]);
    const flow = deserializeFlow('f', 'F', 'Draft', definition as never);
    expect(flow.nodes.map(isStepAllowed)).toEqual([false, false]);
    expect(missingAppStep('other.step')).toBeNull();
    const saved = serializeFlow(flow);
    expect(saved.nodes.map(({ id, type, config }) => ({ id, type, config }))).toEqual(definition.nodes);
  });
});
