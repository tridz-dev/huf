export type FormatMark = 'bold' | 'italic' | 'strike' | 'mono';

export const FORMAT_MARKERS: Record<FormatMark, string> = {
  bold: '*',
  italic: '_',
  strike: '~',
  mono: '```',
};

export interface TextEdit {
  text: string;
  selectionStart: number;
  selectionEnd: number;
}

/**
 * Wrap the selection in the WhatsApp marker, or remove the marker when the
 * selection is already wrapped (either inside the selection or just around it).
 * With an empty selection the marker pair is inserted and the caret placed between.
 */
export function toggleFormat(text: string, start: number, end: number, mark: FormatMark): TextEdit {
  const m = FORMAT_MARKERS[mark];
  const a = Math.max(0, Math.min(start, end, text.length));
  const b = Math.min(text.length, Math.max(start, end));
  const before = text.slice(0, a);
  const selected = text.slice(a, b);
  const after = text.slice(b);

  if (before.endsWith(m) && after.startsWith(m) && (selected !== '' || before.length >= m.length)) {
    return {
      text: before.slice(0, -m.length) + selected + after.slice(m.length),
      selectionStart: a - m.length,
      selectionEnd: b - m.length,
    };
  }
  if (selected.length >= m.length * 2 + 1 && selected.startsWith(m) && selected.endsWith(m)) {
    const inner = selected.slice(m.length, -m.length);
    return { text: before + inner + after, selectionStart: a, selectionEnd: a + inner.length };
  }
  return {
    text: before + m + selected + m + after,
    selectionStart: a + m.length,
    selectionEnd: b + m.length,
  };
}

export interface FormatSegment {
  text: string;
  bold?: boolean;
  italic?: boolean;
  strike?: boolean;
  mono?: boolean;
}

type Style = Omit<FormatSegment, 'text'>;

const MARK_BY_CHAR: Record<string, FormatMark> = { '*': 'bold', _: 'italic', '~': 'strike' };
const isAlnum = (ch: string | undefined) => !!ch && /[\p{L}\p{N}]/u.test(ch);
const isSpace = (ch: string | undefined) => !ch || /\s/.test(ch);

function parse(text: string, style: Style, out: FormatSegment[]): void {
  let buffer = '';
  const flush = () => {
    if (buffer) out.push({ text: buffer, ...style });
    buffer = '';
  };
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (text.startsWith('```', i)) {
      const close = text.indexOf('```', i + 3);
      if (close > i + 3) {
        flush();
        out.push({ text: text.slice(i + 3, close), ...style, mono: true });
        i = close + 3;
        continue;
      }
    }
    const mark = MARK_BY_CHAR[ch];
    if (mark && !isAlnum(text[i - 1]) && !isSpace(text[i + 1]) && text[i + 1] !== ch) {
      let close = -1;
      for (let j = i + 2; j < text.length; j += 1) {
        if (text[j] === '\n') break;
        if (text[j] === ch && !isSpace(text[j - 1]) && !isAlnum(text[j + 1])) {
          close = j;
          break;
        }
      }
      if (close > 0) {
        flush();
        parse(text.slice(i + 1, close), { ...style, [mark]: true }, out);
        i = close + 1;
        continue;
      }
    }
    buffer += ch;
    i += 1;
  }
  flush();
}

/** Split text into styled runs for the preview. Never produces HTML. */
export function renderWhatsAppFormatting(text: string): FormatSegment[] {
  const raw: FormatSegment[] = [];
  parse(text, {}, raw);
  const merged: FormatSegment[] = [];
  for (const seg of raw) {
    const last = merged[merged.length - 1];
    if (
      last &&
      !!last.bold === !!seg.bold &&
      !!last.italic === !!seg.italic &&
      !!last.strike === !!seg.strike &&
      !!last.mono === !!seg.mono
    ) {
      last.text += seg.text;
    } else {
      merged.push({ ...seg });
    }
  }
  return merged;
}
