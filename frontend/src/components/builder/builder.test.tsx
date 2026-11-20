// @vitest-environment jsdom
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AutosaveStatus, savedAgo } from './AutosaveStatus';
import { ErrorSummary, focusFirstError } from './FormSection';
import { CUSTOM_PRESET, PresetSelector } from './PresetSelector';
import { ToggleReveal } from './ToggleReveal';
import { TryPanel } from './TryPanel';
import { Input } from '@/components/ui/input';

describe('AutosaveStatus', () => {
  it('says each state in plain words', () => {
    const now = () => 1_000_000;
    const { rerender } = render(<AutosaveStatus state="dirty" />);
    expect(screen.getByTestId('autosave-status')).toHaveTextContent('Unsaved changes');
    rerender(<AutosaveStatus state="saving" />);
    expect(screen.getByTestId('autosave-status')).toHaveTextContent('Saving…');
    rerender(<AutosaveStatus state="saved" savedAt={1_000_000 - 5_000} now={now} />);
    expect(screen.getByTestId('autosave-status')).toHaveTextContent('Saved just now');
    rerender(<AutosaveStatus state="saved" savedAt={1_000_000 - 4 * 60_000} now={now} />);
    expect(screen.getByTestId('autosave-status')).toHaveTextContent('Saved 4 min ago');
  });

  it('offers Retry on failure', async () => {
    const onRetry = vi.fn();
    render(<AutosaveStatus state="error" onRetry={onRetry} />);
    expect(screen.getByTestId('autosave-status')).toHaveTextContent("Couldn't save · Retry");
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('savedAgo falls back to a time of day after an hour', () => {
    expect(savedAgo(0, 2 * 3600_000)).toMatch(/^at /);
  });
});

describe('ToggleReveal', () => {
  it('reveals its settings only while on', async () => {
    function H() {
      const [on, setOn] = useState(false);
      return (
        <ToggleReveal label="Website widget" description="Chat bubble on your site" checked={on} onCheckedChange={setOn}>
          <p>Allowed domains</p>
        </ToggleReveal>
      );
    }
    render(<H />);
    const sw = screen.getByRole('switch', { name: 'Website widget' });
    expect(sw).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Allowed domains')).toBeNull();
    await userEvent.click(sw);
    expect(sw).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('region', { name: 'Website widget settings' })).toHaveTextContent('Allowed domains');
  });
});

describe('PresetSelector', () => {
  it('moves with arrows and reveals custom controls', async () => {
    function H() {
      const [v, setV] = useState<string>('balanced');
      return (
        <PresetSelector label="Creativity" value={v} onChange={setV}
          presets={[{ value: 'precise', label: 'Precise' }, { value: 'balanced', label: 'Balanced', recommended: true }]}
          custom={<p>Raw slider</p>} />
      );
    }
    render(<H />);
    screen.getByRole('radio', { name: /Balanced/ }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: /Custom/ })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('Raw slider')).toBeInTheDocument();
    expect(CUSTOM_PRESET).toBe('__custom__');
  });
});

describe('inline validation helpers', () => {
  it('focusFirstError focuses the first invalid control; ErrorSummary jumps to fields', async () => {
    render(
      <div data-testid="root">
        <Input aria-label="Name" />
        <Input id="instr" aria-label="Instructions" aria-invalid />
        <ErrorSummary errors={[{ fieldId: 'instr', message: 'Add instructions' }]} />
      </div>,
    );
    expect(focusFirstError(screen.getByTestId('root'))).toBe(true);
    expect(screen.getByLabelText('Instructions')).toHaveFocus();
    screen.getByLabelText('Name').focus();
    await userEvent.click(screen.getByRole('link', { name: 'Add instructions' }));
    expect(screen.getByLabelText('Instructions')).toHaveFocus();
  });
});

describe('TryPanel', () => {
  it('sends on Enter and renders inspector rows', async () => {
    const onSend = vi.fn();
    render(
      <TryPanel draft="hi" onDraftChange={() => {}} onSend={onSend}
        messages={[{ id: '1', from: 'reply', content: 'Hello', inspector: [{ kind: 'source', label: 'Policy.pdf' }, { kind: 'metric', label: '1.8s' }] }]} />,
    );
    expect(screen.getByRole('list', { name: 'Run details' })).toHaveTextContent('Read: Policy.pdf');
    screen.getByRole('textbox', { name: 'Message' }).focus();
    await userEvent.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledOnce();
  });
});
