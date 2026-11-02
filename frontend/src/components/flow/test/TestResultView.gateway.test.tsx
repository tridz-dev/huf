// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TestResultView } from './TestResultView';
import type { StepTestResult } from '@/services/flow/stepTestApi';

afterEach(cleanup);

const result = (output: Record<string, unknown>): StepTestResult => ({
  status: 'success', mode: 'real', output, output_shortened: false, pin_value: output, duration_ms: 0, error: null, fix_hint: null,
  tested_at: new Date().toISOString(), effect: 'reads', calls_ai: false, summary: 'A message came in', preview: null, goes_to: null, branch: null, warnings: [],
});
const pin = { pinned: false, onPin: () => {}, onUnpin: () => {} };

describe('TestResultView for a chat trigger', () => {
  it('keeps record names and ids behind Details and uses plain labels', () => {
    render(<TestResultView result={result({ text: 'Hi', display_name: 'Asha', gateway_event: 'GWE-1', wa_id: '15551', kind: 'message' })} pin={pin} onOpenSetup={() => {}} isTrigger />);
    const main = screen.getByTestId('flow-step-test-output');
    expect(within(main).getByText('Message text')).toBeTruthy();
    expect(within(main).queryByText('Gateway Event')).toBeNull();
    expect(within(main).queryByText('Wa ID')).toBeNull();
    const details = screen.getByTestId('flow-step-test-details');
    expect(details.tagName).toBe('DETAILS');
    expect(within(details).getByText('Message record')).toBeTruthy();
    expect(within(details).getByText('WhatsApp number')).toBeTruthy();
    expect(screen.queryByText('Gateway Event')).toBeNull();
    expect(screen.queryByText('Wa ID')).toBeNull();
  });
  it('leaves other steps alone', () => {
    render(<TestResultView result={result({ name: 'x' })} pin={pin} onOpenSetup={() => {}} isTrigger={false} />);
    expect(screen.queryByTestId('flow-step-test-details')).toBeNull();
  });
});
