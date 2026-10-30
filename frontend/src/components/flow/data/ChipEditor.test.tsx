// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRef } from 'react';
import { makeChip, type Segment } from '@/lib/flow-data/chips';
import type { ChipInfo } from '@/lib/flow-data/model';
import { ChipEditor, type ChipEditorHandle } from './ChipEditor';

const info: ChipInfo = { label: 'Customer name', stepTitle: 'New order', sample: 'Ada Lovelace', missing: false, opaque: false };
const chip = makeChip('input.customer.name', 'Customer name');

function setup(segments: Segment[], extra: Partial<React.ComponentProps<typeof ChipEditor>> = {}) {
  const onSegments = vi.fn();
  const ref = createRef<ChipEditorHandle>();
  const view = render(
    <ChipEditor ref={ref} segments={segments} drawKey="1" describe={() => info} onSegments={onSegments} multiline={false} editable testId="ed" ariaLabel="Subject" {...extra} />
  );
  return { onSegments, ref, box: screen.getByTestId('ed'), view };
}

afterEach(cleanup);

describe('ChipEditor', () => {
  it('draws text and chips, with the example on hover', () => {
    const { box } = setup([{ kind: 'text', text: 'Hi ' }, { kind: 'chip', chip }]);
    const el = box.querySelector('[data-chip]') as HTMLElement;
    expect(box.textContent).toContain('Hi ');
    expect(el.textContent).toContain('Customer name · New order');
    expect(el.title).toBe('Ada Lovelace (example)');
    expect(box.dataset.empty).toBe('false');
  });

  it('an empty box is marked empty so the placeholder shows', () => {
    const { box } = setup([], { placeholder: 'Type, or press / to use data' });
    expect(box.dataset.empty).toBe('true');
    expect(box.dataset.placeholder).toBe('Type, or press / to use data');
  });

  it('x removes the chip', () => {
    const { box, onSegments } = setup([{ kind: 'text', text: 'Hi ' }, { kind: 'chip', chip }]);
    fireEvent.click(box.querySelector('[data-remove]') as HTMLElement);
    expect(onSegments).toHaveBeenCalledWith([{ kind: 'text', text: 'Hi ' }]);
  });

  it('typing reports the new text and keeps the chip by id', () => {
    const { box, onSegments } = setup([{ kind: 'chip', chip }]);
    box.appendChild(document.createTextNode(' - thanks'));
    fireEvent.input(box);
    const last = onSegments.mock.calls.at(-1)?.[0] as Segment[];
    expect(last.map((s) => (s.kind === 'text' ? s.text : s.chip.ref))).toEqual(['input.customer.name', ' - thanks']);
  });

  it('inserting puts the chip at the position and the caret after it', () => {
    const { ref, onSegments } = setup([{ kind: 'text', text: 'Hi  there' }]);
    act(() => ref.current?.insert(chip, 3));
    const segs = onSegments.mock.calls.at(-1)?.[0] as Segment[];
    expect(segs.map((s) => (s.kind === 'text' ? s.text : '[chip]'))).toEqual(['Hi ', '[chip]', ' there']);
  });

  it('a second insert appends after the first', () => {
    const { ref, onSegments } = setup([{ kind: 'chip', chip }]);
    const other = makeChip('input.total', 'Total');
    act(() => ref.current?.insert(other, 1));
    const segs = onSegments.mock.calls.at(-1)?.[0] as Segment[];
    expect(segs.map((s) => (s.kind === 'chip' ? s.chip.ref : s.text))).toEqual(['input.customer.name', 'input.total']);
  });

  it('a slash at the start of a word asks for the picker; elsewhere it is just a character', () => {
    const onSlash = vi.fn(() => true);
    const { box } = setup([{ kind: 'text', text: 'https:' }], { onSlash });
    box.focus();
    const sel = window.getSelection() as Selection;
    const range = document.createRange();
    range.setStart(box.firstChild as Node, 6);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    expect(fireEvent.keyDown(box, { key: '/' })).toBe(true); // not cancelled: typed as a letter
    expect(onSlash).not.toHaveBeenCalled();
  });

  it('a view-only box cannot be edited', () => {
    const { box } = setup([{ kind: 'chip', chip }], { editable: false });
    expect(box.getAttribute('contenteditable')).toBe('false');
    expect(box.querySelector('[data-remove]')).toBeNull();
  });

  it('Enter does not make a new line in a one-line box', () => {
    const { box, onSegments } = setup([{ kind: 'text', text: 'ab' }]);
    expect(fireEvent.keyDown(box, { key: 'Enter' })).toBe(false);
    expect(onSegments).not.toHaveBeenCalled();
  });
});
