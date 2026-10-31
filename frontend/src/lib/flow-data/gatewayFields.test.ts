import { describe, expect, it } from 'vitest';
import { gatewayPickerFields } from './gatewayFields';
import { buildPickerModel, describeChip } from './model';
import { FIXTURE_REGISTRY } from '../flow-gateway/registryFixture';
import type { FlowNode } from '../../types/flow.types';

const spec = FIXTURE_REGISTRY.specs['trigger.whatsapp'];
const trig = (extra: Record<string, unknown> = {}): FlowNode =>
  ({ id: 't', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'WhatsApp message', nodeType: 'trigger', icon: 'x', triggerConfig: { type: 'whatsapp', gateway: 'S' }, ...extra } }) as unknown as FlowNode;
const step = { id: 'a', type: 'action', position: { x: 0, y: 100 }, data: { label: 'Reply', nodeType: 'action', icon: 'x', actionConfig: { type: 'tool-call' } } } as unknown as FlowNode;
const edges = [{ id: 'e', source: 't', target: 'a' }] as never;

describe('gatewayPickerFields', () => {
  const fields = gatewayPickerFields(spec);
  const get = (path: string) => fields.find((f) => f.path === path)!;

  it('uses friendly names and the registry example', () => {
    expect(get('input.text')).toMatchObject({ label: 'Message text', type: 'text', sample: 'Hi, is my order ready?', untrusted: true });
    expect(get('input.display_name')).toMatchObject({ label: 'Sender name', sample: 'Asha' });
    expect(get('input.button_title').label).toBe('Button chosen');
    expect(get('input.received_at').type).toBe('date');
    expect(get('input.is_room').type).toBe('yes_no');
    expect(get('input.attachments')).toMatchObject({ label: 'Files', type: 'list' });
  });

  it('keeps ids out of the lists people pick from', () => {
    expect(get('input.sender_id').advanced_only).toBe(true);
    expect(get('input.gateway_event').advanced_only).toBe(true);
    expect(get('input.text').advanced_only).toBeUndefined();
    const shown = fields.filter((f) => !f.advanced_only).map((f) => f.label);
    expect(shown.join(' ')).not.toMatch(/\bid\b|record/i);
  });

  it('prefers the last real message, field by field', () => {
    const live = gatewayPickerFields(spec, { text: 'Where is my parcel?', display_name: 'Ben' });
    expect(live.find((f) => f.path === 'input.text')!.sample).toBe('Where is my parcel?');
    expect(live.find((f) => f.path === 'input.received_at')!.sample).toBe('2026-01-15 17:15:00'); // not in the real one: registry example
  });

  it('records are not offered as a drill-down with nothing in it', () => {
    expect(get('input.referral').type).toBe('text');
  });
});

describe('picker model for a chat trigger', () => {
  it('lists the registry fields under "Trigger: WhatsApp message" with a chip title of the step name', () => {
    const model = buildPickerModel([trig(), step], edges, 'a', null, 'ancestors', FIXTURE_REGISTRY);
    const first = model.steps[0];
    expect(first.title).toBe('Trigger: WhatsApp message');
    expect(first.source).toBe('example');
    expect(first.hasSample).toBe(true);
    expect(first.root).toBe('input');
    expect(first.fields.some((f) => f.label === 'Message text')).toBe(true);
    const chip = describeChip({ ref: 'input.text' } as never, model);
    expect(chip).toMatchObject({ label: 'Message text', stepTitle: 'WhatsApp message', sample: 'Hi, is my order ready?' });
  });

  it('shows pinned values from the last real message and still hides raw keys', () => {
    const model = buildPickerModel([trig({ sample: { text: 'Hello', sender_id: '1555', secret_thing: 'x' } }), step], edges, 'a', null, 'ancestors', FIXTURE_REGISTRY);
    const labels = model.steps[0].fields.filter((f) => !f.advanced_only).map((f) => f.label);
    expect(labels).not.toContain('Secret thing');
    expect(model.steps[0].source).toBe('pinned');
    expect(model.steps[0].fields.find((f) => f.path === 'input.text')!.sample).toBe('Hello');
  });

  it('offers the last real message (served by the messages endpoint, not the webhook one)', () => {
    expect(buildPickerModel([trig(), step], edges, 'a', null, 'ancestors', FIXTURE_REGISTRY).steps[0].canFetchLast).toBe(true);
  });

  it('without a registry (viewer, failed load) falls back to the sample or the server catalog', () => {
    const model = buildPickerModel([trig({ sample: { text: 'Hello' } }), step], edges, 'a', null);
    expect(model.steps[0].fields.map((f) => f.label)).toContain('Text');
  });
});
