// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FilterBar } from './FilterBar';

describe('FilterBar', () => {
  it('renders the search as an InputGroup at the standard control height', () => {
    const { container } = render(
      <FilterBar searchPlaceholder="Find" searchValue="" onSearchChange={() => {}} />,
    );
    const group = container.querySelector('[data-slot="input-group"]')!;
    expect(group.className).toContain('h-control-sm');
    expect(container.querySelector('[data-slot="input-group-control"]')).toBe(screen.getByPlaceholderText('Find'));
    expect(container.innerHTML).not.toContain('h-[30px]');
  });

  it('propagates changes and submits on Enter', () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    render(<FilterBar searchValue="" onSearchChange={onChange} onSearchSubmit={onSubmit} />);
    const input = screen.getByPlaceholderText('Search...');
    fireEvent.change(input, { target: { value: 'x' } });
    expect(onChange).toHaveBeenCalledWith('x');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalled();
  });

  it('collapsible search opens, focuses and closes (clearing the value)', () => {
    const onChange = vi.fn();
    render(<FilterBar searchValue="abc" onSearchChange={onChange} collapsibleSearch />);
    expect(screen.queryByPlaceholderText('Search...')).toBeNull();
    fireEvent.click(screen.getByLabelText('Open search'));
    expect(screen.getByPlaceholderText('Search...')).toBe(document.activeElement);
    fireEvent.click(screen.getByLabelText('Close search'));
    expect(onChange).toHaveBeenCalledWith('');
    expect(screen.getByLabelText('Open search')).toBeTruthy();
  });
});
