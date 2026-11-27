// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Combobox } from './combobox';

describe('Combobox search', () => {
  it('matches the label, not only the value', async () => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    globalThis.ResizeObserver ||= class { observe() {} unobserve() {} disconnect() {} } as never;
    render(<Combobox options={[{ value: 'PRV-0001', label: 'OpenAI' }, { value: 'PRV-0002', label: 'Anthropic' }]} />);
    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.type(screen.getByPlaceholderText('Search...'), 'anthro');
    expect(screen.getByText('Anthropic')).toBeInTheDocument();
    expect(screen.queryByText('OpenAI')).not.toBeInTheDocument();
  });
});
