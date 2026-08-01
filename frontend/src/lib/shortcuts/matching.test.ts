import { describe, expect, it } from 'vitest';
import { isEditableTarget, matchesBinding, shouldHandleShortcut } from './matching';

function event(overrides: Partial<{
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}> = {}) {
  return {
    key: overrides.key ?? 'b',
    metaKey: overrides.metaKey ?? false,
    ctrlKey: overrides.ctrlKey ?? false,
    shiftKey: overrides.shiftKey ?? false,
    altKey: overrides.altKey ?? false,
  };
}

describe('matchesBinding', () => {
  it('matches Cmd+B on mac via metaKey', () => {
    expect(matchesBinding(event({ key: 'b', metaKey: true }), { key: 'b', mod: true }, 'mac')).toBe(
      true
    );
  });

  it('matches Ctrl+B on windows/linux via ctrlKey', () => {
    expect(
      matchesBinding(event({ key: 'b', ctrlKey: true }), { key: 'b', mod: true }, 'windows')
    ).toBe(true);
  });

  it('does not match when the wrong platform modifier is pressed', () => {
    expect(matchesBinding(event({ key: 'b', ctrlKey: true }), { key: 'b', mod: true }, 'mac')).toBe(
      false
    );
  });

  it('does not match when the required modifier is missing', () => {
    expect(matchesBinding(event({ key: 'b' }), { key: 'b', mod: true }, 'mac')).toBe(false);
  });

  it('is case-insensitive on the key', () => {
    expect(matchesBinding(event({ key: 'B' }), { key: 'b' }, 'mac')).toBe(true);
  });

  it('ignores shift/alt when the binding does not specify them', () => {
    expect(matchesBinding(event({ key: '?', shiftKey: true }), { key: '?' }, 'mac')).toBe(true);
  });

  it('requires shift to match when the binding specifies it', () => {
    expect(
      matchesBinding(event({ key: 'Enter', shiftKey: true }), { key: 'Enter', shift: true }, 'mac')
    ).toBe(true);
    expect(
      matchesBinding(event({ key: 'Enter', shiftKey: false }), { key: 'Enter', shift: true }, 'mac')
    ).toBe(false);
  });
});

describe('isEditableTarget', () => {
  it('treats input, textarea and select as editable', () => {
    expect(isEditableTarget({ tagName: 'INPUT' })).toBe(true);
    expect(isEditableTarget({ tagName: 'TEXTAREA' })).toBe(true);
    expect(isEditableTarget({ tagName: 'SELECT' })).toBe(true);
  });

  it('treats contenteditable elements as editable regardless of tag', () => {
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: true })).toBe(true);
  });

  it('treats other elements as non-editable', () => {
    expect(isEditableTarget({ tagName: 'DIV' })).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });
});

describe('shouldHandleShortcut', () => {
  it('allows shortcuts when focus is not in an editable element', () => {
    expect(
      shouldHandleShortcut({ target: { tagName: 'DIV' }, key: 'k' })
    ).toBe(true);
  });

  it('suppresses shortcuts while typing in an input', () => {
    expect(
      shouldHandleShortcut({ target: { tagName: 'INPUT' }, key: 'k' })
    ).toBe(false);
  });

  it('allows a key in alwaysAllowKeys while typing (e.g. Escape)', () => {
    expect(
      shouldHandleShortcut({
        target: { tagName: 'TEXTAREA' },
        key: 'Escape',
        alwaysAllowKeys: ['Escape'],
      })
    ).toBe(true);
  });

  it('respects a custom alwaysAllowKeys list', () => {
    expect(
      shouldHandleShortcut({
        target: { tagName: 'INPUT' },
        key: 'Enter',
        alwaysAllowKeys: ['Enter'],
      })
    ).toBe(true);
  });

  it('allows any key in editable elements when allowInEditable is set', () => {
    expect(
      shouldHandleShortcut({ target: { tagName: 'INPUT' }, key: 'k', allowInEditable: true })
    ).toBe(true);
  });
});
