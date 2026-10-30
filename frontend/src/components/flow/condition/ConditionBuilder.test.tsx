// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { FlowNode } from '@/types/flow.types';
import { buildPickerModel } from '@/lib/flow-data/model';

const trigger = {
  id: 'start',
  type: 'trigger',
  position: { x: 0, y: 0 },
  data: { nodeType: 'trigger', label: 'New order', triggerConfig: { type: 'webhook' }, sample: { amount: 150, status: 'Paid', customer: { name: 'Ada' } } },
} as unknown as FlowNode;
const model = buildPickerModel([trigger], [], 'check', null);

vi.mock('../data/useDataCatalog', () => ({ useDataCatalog: () => ({ model, loading: false, refresh: () => {} }), invalidateDataCatalog: () => {} }));
vi.mock('@/contexts/FlowContext', () => ({ useFlowContext: () => ({ activeFlow: null, updateNodeData: () => {} }) }));
vi.mock('@/lib/ui/responsive', () => ({ useViewport: () => ({ isPhone: false }) }));

import { ConditionBuilder } from './ConditionBuilder';

afterEach(cleanup);

function Host({ initial, onText, disabled }: { initial: string; onText: (t: string) => void; disabled?: boolean }) {
  const [text, setText] = useState(initial);
  return (
    <>
      <ConditionBuilder nodeId="check" expression={text} disabled={disabled} onChange={(t) => { setText(t); onText(t); }} />
      <button type="button" onClick={() => setText("input['x'] == 'outside'")}>outside</button>
    </>
  );
}

const RULES = "number(input['amount']) > 100 and input['status'] == 'Paid'";

describe('ConditionBuilder', () => {
  it('shows each rule from the text, with the sentence', () => {
    render(<Host initial={RULES} onText={() => {}} />);
    expect(screen.getByTestId('flow-condition-row-0-field').textContent).toContain('Amount');
    expect(screen.getByTestId('flow-condition-row-0-op').textContent).toContain('is more than');
    expect((screen.getByTestId('flow-condition-row-0-value') as HTMLInputElement).value).toBe('100');
    expect((screen.getByTestId('flow-condition-row-1-value') as HTMLInputElement).value).toBe('Paid');
    expect(screen.getByTestId('flow-condition-sentence-text').textContent).toBe('Amount is more than 100 and Status is Paid');
    expect(screen.getByTestId('flow-condition-match-all').getAttribute('aria-checked')).toBe('true');
  });

  it('starts an empty step with one empty row and no text', () => {
    const onText = vi.fn();
    render(<Host initial="" onText={onText} />);
    expect(screen.getByTestId('flow-condition-row-0')).toBeTruthy();
    expect(screen.getByTestId('flow-condition-sentence-empty')).toBeTruthy();
    expect(onText).not.toHaveBeenCalled();
  });

  it('typing a value writes the text; an unfinished rule is left out', () => {
    const onText = vi.fn();
    render(<Host initial={RULES} onText={onText} />);
    fireEvent.change(screen.getByTestId('flow-condition-row-0-value'), { target: { value: '250' } });
    expect(onText).toHaveBeenLastCalledWith("number(input['amount']) > 250 and input['status'] == 'Paid'");
    // clearing the value of the second rule leaves it unfinished: only the first rule is kept
    fireEvent.change(screen.getByTestId('flow-condition-row-1-value'), { target: { value: '' } });
    expect(onText).toHaveBeenLastCalledWith("number(input['amount']) > 250");
    expect(screen.getByTestId('flow-condition-row-1-unfinished').textContent).toContain('value');
  });

  it('a value that looks like code stays text', () => {
    const onText = vi.fn();
    render(<Host initial="input['status'] == 'x'" onText={onText} />);
    fireEvent.change(screen.getByTestId('flow-condition-row-0-value'), { target: { value: "' or True or '" } });
    expect(onText).toHaveBeenLastCalledWith("input['status'] == '\\' or True or \\''");
  });

  it('Any of changes how the rules are joined', () => {
    const onText = vi.fn();
    render(<Host initial={RULES} onText={onText} />);
    fireEvent.click(screen.getByTestId('flow-condition-match-any'));
    expect(onText).toHaveBeenLastCalledWith("number(input['amount']) > 100 or input['status'] == 'Paid'");
    expect(screen.getByTestId('flow-condition-sentence-text').textContent).toBe('Amount is more than 100 or Status is Paid');
  });

  it('removes a rule and adds one; a group is one level deep', () => {
    const onText = vi.fn();
    render(<Host initial={RULES} onText={onText} />);
    fireEvent.click(screen.getByTestId('flow-condition-row-0-remove'));
    expect(onText).toHaveBeenLastCalledWith("input['status'] == 'Paid'");
    fireEvent.click(screen.getByTestId('flow-condition-add-group'));
    expect(screen.getByTestId('flow-condition-group-1')).toBeTruthy();
    expect(screen.getByTestId('flow-condition-group-1-row-0')).toBeTruthy();
    expect(screen.queryByTestId('flow-condition-group-1-add-group')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-condition-group-1-add-rule'));
    expect(screen.getByTestId('flow-condition-group-1-row-1')).toBeTruthy();
  });

  it('shows a group read from the text, and a group with one rule keeps its brackets', () => {
    render(<Host initial="input['a'] == 'x' and (input['status'] == 'Paid' or input['status'] == 'Shipped')" onText={() => {}} />);
    expect(screen.getByTestId('flow-condition-group-1-match-any').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('flow-condition-group-1-row-1-value')).toBeTruthy();
  });

  it('follows a change of the text from outside (undo)', () => {
    render(<Host initial={RULES} onText={() => {}} />);
    fireEvent.click(screen.getByText('outside'));
    expect((screen.getByTestId('flow-condition-row-0-value') as HTMLInputElement).value).toBe('outside');
    expect(screen.queryByTestId('flow-condition-row-1')).toBeNull();
  });

  it('shows no editing buttons when disabled', () => {
    render(<Host initial={RULES} onText={() => {}} disabled />);
    expect(screen.queryByTestId('flow-condition-add-rule')).toBeNull();
    expect(screen.queryByTestId('flow-condition-row-0-remove')).toBeNull();
    expect((screen.getByTestId('flow-condition-row-0-value') as HTMLInputElement).disabled).toBe(true);
  });

  it('warns when there are too many rules to save', () => {
    const long = Array.from({ length: 12 }, (_, i) => `input['field_number_${i}'] == 'some value ${i}'`).join(' and ');
    render(<Host initial={long} onText={() => {}} />);
    expect(screen.getByTestId('flow-condition-too-long')).toBeTruthy();
  });
});
