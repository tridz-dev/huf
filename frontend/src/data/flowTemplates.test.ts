import { describe, expect, it } from 'vitest';
import { FLOW_TEMPLATES, TEMPLATE_GROUPS, templateSteps, templateTrigger } from './flowTemplates';

describe('flow templates catalog', () => {
  it('has unique ids and plain, complete text', () => {
    const ids = FLOW_TEMPLATES.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const t of FLOW_TEMPLATES) {
      expect(t.name.length).toBeGreaterThan(3);
      expect(t.description.endsWith('.')).toBe(true);
      expect(t.description).not.toMatch(/->|\{|\}/);
      expect(TEMPLATE_GROUPS).toContain(t.group);
    }
  });

  it('carries nothing that belongs to the site it was copied from', () => {
    const text = JSON.stringify(FLOW_TEMPLATES);
    expect(text).not.toMatch(/"secret"/);
    expect(text).not.toMatch(/C0CCDGTDBHR|example\.com"\s*,\s*"subject|Huf Demo Agent/);
    for (const t of FLOW_TEMPLATES) {
      for (const n of t.graph.nodes) {
        if (n.type === 'agent.run') expect(n.config.agent).toBe('');
        if (n.type === 'output') expect(n).not.toHaveProperty('next');
      }
    }
  });

  it('is a connected graph: every step is reachable from the trigger', () => {
    for (const t of FLOW_TEMPLATES) {
      const byId = new Map(t.graph.nodes.map((n) => [n.id, n]));
      const links = (id: string): string[] => {
        const n = byId.get(id)!;
        const c = n.config as Record<string, unknown>;
        const out: unknown[] = [n.next, c.on_true, c.on_false, c.approve_next, c.reject_next, c.default, ...(Array.isArray(c.body) ? c.body : [])];
        for (const o of (c.options as Array<{ node_id: string }>) ?? []) out.push(o.node_id);
        return out.filter((x): x is string => typeof x === 'string');
      };
      const seen = new Set<string>();
      const queue = [...(Array.isArray(t.graph.entry) ? t.graph.entry : [t.graph.entry])];
      while (queue.length) {
        const id = queue.pop()!;
        if (seen.has(id)) continue;
        seen.add(id);
        queue.push(...links(id));
      }
      expect([...byId.keys()].filter((id) => !seen.has(id)), t.id).toEqual([]);
    }
  });

  it('lists steps after the trigger and knows the trigger kind', () => {
    const cond = FLOW_TEMPLATES.find((t) => t.id === 'big-or-small')!;
    expect(templateSteps(cond).map((s) => s.type)).toEqual(['condition', 'output', 'output']);
    expect(templateTrigger(cond)).toBe('webhook');
    expect(templateTrigger(FLOW_TEMPLATES.find((t) => t.id === 'every-hour')!)).toBe('schedule');
    expect(templateTrigger(FLOW_TEMPLATES.find((t) => t.id === 'record-created')!)).toBe('doc-event');
    expect(templateSteps(FLOW_TEMPLATES.find((t) => t.id === 'post-to-slack')!)[0]).toEqual({ type: 'tool.call', tool_id: 'slack_send_message' });
  });
});

describe('chat templates', () => {
  it('start from a WhatsApp or Telegram message with the channel left blank for the gallery to ask', () => {
    for (const id of ['whatsapp-agent-reply', 'telegram-keyword-reply']) {
      const t = FLOW_TEMPLATES.find((x) => x.id === id)!;
      expect(t).toBeDefined();
      const trigger = t.graph.nodes.find((n) => n.type.startsWith('trigger.'))!;
      expect(trigger.config.gateway).toBe('');
      expect(t.graph.nodes.map((n) => n.type)).toEqual([trigger.type, 'agent.run', 'output']);
      const end = t.graph.nodes.find((n) => n.type === 'output')!;
      expect((end.config as { outcome?: { label: string } }).outcome?.label).toMatch(/Answered/);
    }
    expect(templateTrigger(FLOW_TEMPLATES.find((t) => t.id === 'whatsapp-agent-reply')!)).toBe('whatsapp');
    expect(templateTrigger(FLOW_TEMPLATES.find((t) => t.id === 'telegram-keyword-reply')!)).toBe('telegram');
  });
});
