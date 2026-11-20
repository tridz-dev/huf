// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
// @vitest-environment jsdom
import { useForm } from 'react-hook-form';
// @vitest-environment jsdom
import { SourceSettingsSheet } from './SourceSettingsSheet';
// @vitest-environment jsdom
import { SourceHistorySheet } from './SourceHistorySheet';
// @vitest-environment jsdom

// @vitest-environment jsdom
vi.mock('../GeneralTab', () => ({ GeneralTab: () => <div>general</div> }));
// @vitest-environment jsdom
vi.mock('../KnowledgeActivityTab', () => ({ KnowledgeActivityTab: () => <div>activity</div> }));
// @vitest-environment jsdom

// @vitest-environment jsdom
function Harness({ dirty, onDelete }: { dirty: boolean; onDelete: () => void }) {
// @vitest-environment jsdom
  const form = useForm<any>({ defaultValues: { source_name: 'Docs', description: '', disabled: 0 } });
// @vitest-environment jsdom
  return (
// @vitest-environment jsdom
    <SourceSettingsSheet open onOpenChange={() => {}} form={form} source={{ name: 's1', source_name: 'Docs' } as any}
// @vitest-environment jsdom
      providers={[]} documentCount={1241} dirty={dirty} saving={false} onSave={() => {}} onDelete={onDelete} />
// @vitest-environment jsdom
  );
// @vitest-environment jsdom
}
// @vitest-environment jsdom

// @vitest-environment jsdom
describe('source sheets', () => {
// @vitest-environment jsdom
  it('renders sections and keeps Save disabled when not dirty', () => {
// @vitest-environment jsdom
    render(<Harness dirty={false} onDelete={() => {}} />);
// @vitest-environment jsdom
    expect(screen.getByText('Delete this source')).toBeTruthy();
// @vitest-environment jsdom
    expect(screen.getByText(/Removes all 1,241 documents/)).toBeTruthy();
// @vitest-environment jsdom
    expect((screen.getByTestId('save-settings') as HTMLButtonElement).disabled).toBe(true);
// @vitest-environment jsdom
  });
// @vitest-environment jsdom
  it('Delete calls onDelete', () => {
// @vitest-environment jsdom
    const onDelete = vi.fn();
// @vitest-environment jsdom
    render(<Harness dirty onDelete={onDelete} />);
// @vitest-environment jsdom
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
// @vitest-environment jsdom
    expect(onDelete).toHaveBeenCalled();
// @vitest-environment jsdom
  });
// @vitest-environment jsdom
  it('history sheet shows activity', () => {
// @vitest-environment jsdom
    render(<SourceHistorySheet open onOpenChange={() => {}} knowledgeSource="s1" refreshKey={0} />);
// @vitest-environment jsdom
    expect(screen.getByText('History')).toBeTruthy();
// @vitest-environment jsdom
    expect(screen.getByText('activity')).toBeTruthy();
// @vitest-environment jsdom
  });
// @vitest-environment jsdom
});
