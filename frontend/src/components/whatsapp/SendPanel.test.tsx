// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('./TemplateSend', () => ({ TemplateSend: () => <div /> }));
import { SendPanel } from './SendPanel';

function open() {
  return render(<SendPanel gateway="GW-1" onSent={() => {}} openRequested onOpenHandled={() => {}} />);
}

describe('SendPanel recipient row', () => {
  it('puts To and Message type in one FieldRow, both labelled', () => {
    const { container } = open();
    const row = container.querySelector('[data-field-row]')!;
    expect(row).not.toBeNull();
    const labels = row.querySelectorAll('[data-field-label] label');
    expect([...labels].map((l) => l.textContent)).toEqual(['To', 'Message type']);
    expect(row.querySelectorAll('label')).toHaveLength(2); // no raw labels outside Field
    expect(screen.getByLabelText('To')).toHaveAttribute('id', 'whatsapp-send-to');
  });

  it('labels the type picker and leaves no h-* overrides on the row controls', () => {
    const { container } = open();
    const picker = screen.getByRole('combobox', { name: 'Message type' });
    expect(picker).toHaveAttribute('id', 'whatsapp-send-type');
    expect(container.querySelector('label[for="whatsapp-send-type"]')).toHaveTextContent('Message type');
    for (const el of [picker, screen.getByLabelText('To')]) expect(el.className).not.toMatch(/(^|\s)h-\d/);
  });
});
