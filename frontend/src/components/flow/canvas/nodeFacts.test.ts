// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { cardTitle, stepAriaLabel, stepOrder } from './nodeFacts';

describe('stepAriaLabel', () => {
  it('says where the step is, what it is and how it stands', () => {
    expect(stepAriaLabel(3, 7, 'Send email', 'Needs setup')).toBe('Step 3 of 7: Send email, needs setup');
    expect(stepAriaLabel(1, 1, 'Webhook', 'Done')).toBe('Step 1 of 1: Webhook, done');
  });
});

describe('stepOrder', () => {
  it('numbers steps top to bottom, then left to right', () => {
    const order = stepOrder([
      { id: 'c', position: { x: 400, y: 410 } },
      { id: 'a', position: { x: 250, y: 100 } },
      { id: 'b2', position: { x: 395, y: 250 } },
      { id: 'b1', position: { x: 105, y: 250 } },
    ]);
    expect([...order.entries()].sort((x, y) => x[1] - y[1]).map(([id]) => id)).toEqual(['a', 'b1', 'b2', 'c']);
  });
  it('treats steps a few pixels apart in height as one row', () => {
    const order = stepOrder([{ id: 'r', position: { x: 300, y: 252 } }, { id: 'l', position: { x: 100, y: 258 } }]);
    expect(order.get('l')).toBe(1);
  });
});

describe('cardTitle', () => {
  it('shows "Start here" for the trigger nobody chose yet and the label otherwise', () => {
    expect(cardTitle({ label: 'Select trigger', nodeType: 'trigger', configured: false })).toBe('Start here');
    expect(cardTitle({ label: 'Webhook', nodeType: 'trigger', configured: true, triggerConfig: { type: 'webhook' } as never })).toBe('Webhook');
    expect(cardTitle({ label: 'Send', nodeType: 'action', configured: true })).toBe('Send');
  });
});
