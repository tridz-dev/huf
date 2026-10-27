import { describe, expect, it } from 'vitest';
import { renderWhatsAppFormatting, toggleFormat } from './formatting';

describe('toggleFormat', () => {
  it('wraps a selection and keeps it selected', () => {
    expect(toggleFormat('hello world', 6, 11, 'bold')).toEqual({ text: 'hello *world*', selectionStart: 7, selectionEnd: 12 });
    expect(toggleFormat('hi', 0, 2, 'italic').text).toBe('_hi_');
    expect(toggleFormat('hi', 0, 2, 'strike').text).toBe('~hi~');
    expect(toggleFormat('hi', 0, 2, 'mono').text).toBe('```hi```');
  });

  it('unwraps when markers surround the selection', () => {
    expect(toggleFormat('a *b* c', 3, 4, 'bold')).toEqual({ text: 'a b c', selectionStart: 2, selectionEnd: 3 });
  });

  it('unwraps when the selection includes the markers', () => {
    expect(toggleFormat('a *b* c', 2, 5, 'bold')).toEqual({ text: 'a b c', selectionStart: 2, selectionEnd: 3 });
  });

  it('inserts a pair around the caret when nothing is selected', () => {
    expect(toggleFormat('ab', 1, 1, 'bold')).toEqual({ text: 'a**b', selectionStart: 2, selectionEnd: 2 });
  });

  it('does not unwrap a different marker', () => {
    expect(toggleFormat('_b_', 1, 2, 'bold').text).toBe('_*b*_');
  });

  it('accepts a reversed selection', () => {
    expect(toggleFormat('abc', 3, 0, 'bold').text).toBe('*abc*');
  });
});

describe('renderWhatsAppFormatting', () => {
  it('renders each style', () => {
    expect(renderWhatsAppFormatting('a *b* _c_ ~d~ ```e```')).toEqual([
      { text: 'a ' },
      { text: 'b', bold: true },
      { text: ' ' },
      { text: 'c', italic: true },
      { text: ' ' },
      { text: 'd', strike: true },
      { text: ' ' },
      { text: 'e', mono: true },
    ]);
  });

  it('nests styles', () => {
    expect(renderWhatsAppFormatting('*bold _both_*')).toEqual([
      { text: 'bold ', bold: true },
      { text: 'both', bold: true, italic: true },
    ]);
  });

  it('leaves unmatched or spaced markers as text', () => {
    expect(renderWhatsAppFormatting('2 * 3 * 4')).toEqual([{ text: '2 * 3 * 4' }]);
    expect(renderWhatsAppFormatting('*open')).toEqual([{ text: '*open' }]);
    expect(renderWhatsAppFormatting('snake_case_name')).toEqual([{ text: 'snake_case_name' }]);
    expect(renderWhatsAppFormatting('**')).toEqual([{ text: '**' }]);
  });

  it('does not span lines and never turns markup into html', () => {
    expect(renderWhatsAppFormatting('*a\nb*')).toEqual([{ text: '*a\nb*' }]);
    expect(renderWhatsAppFormatting('<b>*x*</b>')).toEqual([{ text: '<b>' }, { text: 'x', bold: true }, { text: '</b>' }]);
  });

  it('keeps mono content raw', () => {
    expect(renderWhatsAppFormatting('```*x*```')).toEqual([{ text: '*x*', mono: true }]);
  });

  it('handles empty text', () => {
    expect(renderWhatsAppFormatting('')).toEqual([]);
  });
});
