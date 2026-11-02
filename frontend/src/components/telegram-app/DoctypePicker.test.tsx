// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { DoctypePicker } from './DoctypePicker';
import { doctypeChoices, filterChoices } from './model';
import type { TgConfig } from '@/services/telegramAppApi';

describe('DoctypePicker', () => {
  it('filters as you type, uses plain copy, and reports the pick', () => {
    const onChange = vi.fn();
    render(<DoctypePicker choices={['Customer', 'Sales Order', 'Sales Invoice']} value="" onChange={onChange} />);
    const box = screen.getByRole('combobox', { name: 'Record type' });
    expect(box).toHaveAttribute('placeholder', 'What are you looking for?');
    fireEvent.change(box, { target: { value: 'sales' } });
    expect(screen.getAllByRole('option')).toHaveLength(2);
    fireEvent.click(screen.getByText('Sales Order'));
    expect(onChange).toHaveBeenLastCalledWith('Sales Order');
  });

  it('says so when nothing matches', () => {
    render(<DoctypePicker choices={['Customer']} value="" onChange={() => {}} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'zzz' } });
    expect(screen.getByText('Nothing matches that.')).toBeInTheDocument();
  });
});

describe('model', () => {
  it('maps config doctypes and filters', () => {
    expect(doctypeChoices({ doctypes: [{ name: 'Item' }] } as TgConfig)).toEqual(['Item']);
    expect(doctypeChoices(null)).toEqual([]);
    expect(filterChoices(['A1', 'B1', 'A2'], 'a', 1)).toEqual(['A1']);
  });
});
