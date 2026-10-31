import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { chipAfter, chipBefore, insertChip, lengthOf, removeChip, type Chip, type Segment } from '@/lib/flow-data/chips';
import type { ChipInfo } from '@/lib/flow-data/model';
import { caretPosition, readSegments, renderSegments, setCaret } from './chipDom';

export interface ChipEditorHandle {
  /** Caret position (one per character and per chip); the end when the box is not focused. */
  position(): number;
  focus(position?: number): void;
  /** Put `chip` at `position`. */
  insert(chip: Chip, position: number): void;
  /** Type `text` at `position` (the `/` that opened the picker, when it is closed without a pick). */
  insertText(text: string, position: number): void;
  replace(id: string, next: Chip): void;
}

interface ChipEditorProps {
  segments: Segment[];
  /** Changes whenever the box must be drawn again from `segments` (an outside change, new labels or examples). */
  drawKey: string;
  describe: (chip: Chip) => ChipInfo;
  onSegments: (segments: Segment[]) => void;
  multiline: boolean;
  /** Chips only: the person picks data, typing does nothing (a field that stores a reference). */
  pickOnly?: boolean;
  editable: boolean;
  placeholder?: string;
  id?: string;
  testId?: string;
  ariaLabel?: string;
  ariaDescribedBy?: string;
  inputMode?: 'text' | 'decimal' | 'url';
  /** Typed `/` at the start of a word: open the picker. Returns true when it did, so the slash is not typed. */
  onSlash?: (position: number) => boolean;
  onChipClick?: (chip: Chip) => void;
  className?: string;
}

/**
 * One editable box where typed text and data chips mix. Chips are small pills ("Customer name · New order") you can click to
 * change, remove with x or Backspace, and move around like letters. Typing never leaves the box: the stored form is made
 * from the segment list, not from the screen.
 */
export const ChipEditor = forwardRef<ChipEditorHandle, ChipEditorProps>(function ChipEditor(
  { segments, drawKey, describe, onSegments, multiline, pickOnly, editable, placeholder, id, testId, ariaLabel, ariaDescribedBy, inputMode, onSlash, onChipClick, className },
  ref
) {
  const root = useRef<HTMLDivElement>(null);
  const live = useRef(segments);
  live.current = segments;
  const chips = useRef(new Map<string, Chip>());
  const handlers = useRef({ onSegments, onSlash, onChipClick, describe });
  handlers.current = { onSegments, onSlash, onChipClick, describe };

  const remember = (segs: Segment[]) => {
    chips.current = new Map(segs.flatMap((s) => (s.kind === 'chip' ? [[s.chip.id, s.chip] as const] : [])));
  };

  const draw = useCallback(
    (segs: Segment[], caret?: number) => {
      const el = root.current;
      if (!el) return;
      remember(segs);
      renderSegments(el, segs, (c) => handlers.current.describe(c), editable);
      if (caret !== undefined) setCaret(el, caret);
    },
    [editable]
  );

  // Draw again when asked to (outside change, new examples), keeping the caret where it was.
  useLayoutEffect(() => {
    const el = root.current;
    const focused = !!el && document.activeElement === el;
    const caret = focused && el ? caretPosition(el) : null;
    draw(live.current, caret ?? undefined);
  }, [drawKey, draw]);

  const emit = (segs: Segment[], caret?: number) => {
    live.current = segs;
    handlers.current.onSegments(segs);
    draw(segs, caret);
  };

  useImperativeHandle(ref, () => ({
    position: () => (root.current && caretPosition(root.current)) ?? lengthOf(live.current),
    focus: (position) => {
      const el = root.current;
      if (!el) return;
      el.focus();
      setCaret(el, position ?? lengthOf(live.current));
    },
    insert: (chip, position) => {
      emit(insertChip(live.current, position, chip), position + 1);
      if (root.current) {
        root.current.focus();
        setCaret(root.current, position + 1);
      }
    },
    insertText: (text, position) => {
      root.current?.focus();
      if (root.current) setCaret(root.current, position);
      typeText(text);
    },
    replace: (idToReplace, next) => {
      const segs = live.current.map((s) => (s.kind === 'chip' && s.chip.id === idToReplace ? ({ kind: 'chip', chip: { ...next, id: idToReplace } } as Segment) : s));
      emit(segs);
    },
  }));

  // The box reports typing; chips are looked up by id so a typed-over chip keeps its reference.
  const onInput = () => {
    const el = root.current;
    if (!el) return;
    const segs = readSegments(el, chips.current);
    live.current = segs;
    el.dataset.empty = segs.length === 0 ? 'true' : 'false';
    handlers.current.onSegments(segs);
  };

  const typeText = (text: string) => {
    const el = root.current;
    if (!el) return;
    const segs = readSegments(el, chips.current);
    const at = caretPosition(el) ?? lengthOf(segs);
    const clean = multiline ? text : text.replace(/\s*\n\s*/g, ' ');
    const next: Segment[] = [];
    let pos = 0;
    let done = false;
    for (const s of segs) {
      const size = s.kind === 'text' ? s.text.length : 1;
      if (!done && s.kind === 'text' && at >= pos && at <= pos + size) {
        next.push({ kind: 'text', text: s.text.slice(0, at - pos) + clean + s.text.slice(at - pos) });
        done = true;
      } else if (!done && at <= pos) {
        next.push({ kind: 'text', text: clean }, s);
        done = true;
      } else next.push(s);
      pos += size;
    }
    if (!done) next.push({ kind: 'text', text: clean });
    emit(next, at + clean.length);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const el = root.current;
    if (!el || !editable) return;
    const sel = window.getSelection();
    const collapsed = !!sel && sel.isCollapsed;
    if (e.key === 'Enter') {
      e.preventDefault();
      if (multiline) typeText('\n');
      return;
    }
    if (e.key === '/' && !e.metaKey && !e.ctrlKey && !e.altKey && handlers.current.onSlash) {
      const segs = readSegments(el, chips.current);
      const at = caretPosition(el) ?? lengthOf(segs);
      const before = segs.map((s) => (s.kind === 'text' ? s.text : '\u0000')).join('').slice(0, at);
      if ((before === '' || /\s$/.test(before)) && collapsed && handlers.current.onSlash(at)) e.preventDefault();
      return;
    }
    if (pickOnly && e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      return;
    }
    if (!collapsed) return;
    if (e.key === 'Backspace' || e.key === 'Delete') {
      const segs = readSegments(el, chips.current);
      const at = caretPosition(el) ?? 0;
      const chip = e.key === 'Backspace' ? chipBefore(segs, at) : chipAfter(segs, at);
      if (chip) {
        e.preventDefault();
        emit(removeChip(segs, chip.id), e.key === 'Backspace' ? at - 1 : at);
      }
    }
  };

  const onPaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (editable && !pickOnly) typeText(e.clipboardData.getData('text/plain'));
  };

  const onClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const remove = target.closest<HTMLElement>('[data-remove]');
    if (remove && editable) {
      e.preventDefault();
      const next = removeChip(readSegments(root.current as HTMLElement, chips.current), remove.dataset.remove as string);
      emit(next, undefined);
      root.current?.focus();
      return;
    }
    const chipEl = target.closest<HTMLElement>('[data-chip]');
    const chip = chipEl ? chips.current.get(chipEl.dataset.chip as string) : undefined;
    if (chip && editable) handlers.current.onChipClick?.(chip);
  };

  // A chip with the keyboard: Enter on a focused chip changes it, Backspace removes it.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const onKey = (e: KeyboardEvent) => {
      const chipEl = (e.target as HTMLElement).closest<HTMLElement>('[data-chip]');
      if (!chipEl || !editable) return;
      const chip = chips.current.get(chipEl.dataset.chip as string);
      if (!chip) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        handlers.current.onChipClick?.(chip);
      } else if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault();
        emit(removeChip(readSegments(el, chips.current), chip.id));
        el.focus();
      }
    };
    el.addEventListener('keydown', onKey);
    return () => el.removeEventListener('keydown', onKey);
  });

  return (
    <div
      ref={root}
      id={id}
      data-testid={testId}
      data-empty="true"
      data-placeholder={placeholder}
      role="textbox"
      aria-multiline={multiline}
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy}
      aria-readonly={!editable}
      aria-disabled={editable ? undefined : true}
      contentEditable={editable}
      suppressContentEditableWarning
      inputMode={inputMode}
      spellCheck={false}
      className={cn(
        'min-w-0 whitespace-pre-wrap break-words px-3 py-1.5 text-ui-text outline-none',
        'data-[empty=true]:before:pointer-events-none data-[empty=true]:before:text-muted-foreground data-[empty=true]:before:content-[attr(data-placeholder)]',
        multiline ? 'min-h-[88px] max-h-60 overflow-y-auto' : 'min-h-9 overflow-x-hidden',
        className
      )}
      onInput={onInput}
      onKeyDown={onKeyDown}
      onPaste={onPaste}
      onBeforeInput={(e) => { if (pickOnly && (e.nativeEvent as InputEvent).inputType?.startsWith('insert')) e.preventDefault(); }}
      onClick={onClick}
      onDrop={(e) => e.preventDefault()}
    />
  );
});
