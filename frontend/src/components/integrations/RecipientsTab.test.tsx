// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useForm } from 'react-hook-form';
import { RecipientsTab } from './RecipientsTab';

function Harness() {
  const form = useForm<any>({
    defaultValues: {
      recipients: [
        { recipient_name: 'A', recipient_id: '1', user: '' },
        { recipient_name: 'B', recipient_id: '2', user: '' },
      ],
    },
  });
  return <RecipientsTab form={form} />;
}

describe('RecipientsTab', () => {
  it('renders each recipient as a FieldRow of 3 Fields plus a FieldAction', () => {
    const { container } = render(<Harness />);
    const rows = container.querySelectorAll('[data-field-row]');
    expect(rows).toHaveLength(2);
    rows.forEach((row) => {
      const cells = Array.from(row.children);
      expect(cells).toHaveLength(4);
      cells.forEach((c) => {
        expect(c.querySelector('[data-field-label]')).not.toBeNull();
        expect(c.querySelector('[data-field-note]')).not.toBeNull();
      });
      expect(cells[3].querySelector('[data-field-label]')?.getAttribute('aria-hidden')).toBe('true');
      expect(cells[3].querySelector('button[aria-label="Remove recipient"]')).not.toBeNull();
    });
  });

  it('has no bare controls directly inside a row', () => {
    const { container } = render(<Harness />);
    container.querySelectorAll('[data-field-row]').forEach((row) => {
      Array.from(row.children).forEach((c) => {
        expect(['INPUT', 'BUTTON', 'SELECT']).not.toContain(c.tagName);
      });
    });
  });

  it('removes a recipient via the trash button', () => {
    const { container } = render(<Harness />);
    fireEvent.click(screen.getAllByLabelText('Remove recipient')[0]);
    expect(container.querySelectorAll('[data-field-row]')).toHaveLength(1);
  });
});
