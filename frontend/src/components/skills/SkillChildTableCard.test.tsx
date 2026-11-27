// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Server } from 'lucide-react';
import { ChildTableCard } from './SkillChildTableCard';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};

describe('ChildTableCard', () => {
  it('adds several picked values in a single onAdd call', () => {
    const onAdd = vi.fn();
    render(
      <ChildTableCard
        title="Tools"
        description="d"
        icon={Server}
        emptyText="none"
        addLabel="Add Tool"
        options={[
          { value: 'a', label: 'Alpha' },
          { value: 'b', label: 'Beta' },
          { value: 'c', label: 'Gamma' },
        ]}
        onAdd={onAdd}
      >
        {[]}
      </ChildTableCard>
    );
    expect(screen.getByRole('button', { name: /Add Tool/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('combobox'));
    for (const label of ['Alpha', 'Beta', 'Gamma']) {
      fireEvent.click(screen.getByText(label));
    }
    fireEvent.click(screen.getByRole('button', { name: /Add Tool \(3\)/ }));
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd).toHaveBeenCalledWith(['a', 'b', 'c']);
  });
});
