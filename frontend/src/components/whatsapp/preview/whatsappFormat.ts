export type FormatNode =
  | { kind: 'text'; value: string }
  | { kind: 'mono'; value: string }
  | { kind: 'bold' | 'italic' | 'strike'; children: FormatNode[] };

const MARKERS: Record<string, 'bold' | 'italic' | 'strike'> = { '*': 'bold', _: 'italic', '~': 'strike' };
const isSpace = (c: string | undefined) => c === undefined || /\s/.test(c);
const isWord = (c: string | undefined) => c !== undefined && /[\p{L}\p{N}]/u.test(c);

function pushText(out: FormatNode[], value: string) {
  if (!value) return;
  const last = out[out.length - 1];
  if (last?.kind === 'text') last.value += value;
  else out.push({ kind: 'text', value });
}

function findClose(text: string, from: number, marker: string): number {
  for (let j = from; j < text.length; j++) {
    const c = text[j];
    if (c === '\n') return -1;
    if (c === '\\' && (text[j + 1] in MARKERS || text[j + 1] === '\\')) {
      j++;
      continue;
    }
    if (c === marker && !isSpace(text[j - 1]) && !isWord(text[j + 1])) return j;
  }
  return -1;
}

/**
 * Parses WhatsApp message formatting (*bold*, _italic_, ~strike~, ```mono```).
 * Markers must hug their content and sit on word boundaries; unclosed markers
 * stay literal; a backslash before a marker escapes it. Pure data out: callers
 * render the nodes as React elements, never as HTML.
 */
export function parseWhatsAppFormat(text: string): FormatNode[] {
  const out: FormatNode[] = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === '\\' && (text[i + 1] in MARKERS || text[i + 1] === '\\')) {
      pushText(out, text[i + 1]);
      i += 2;
      continue;
    }
    if (text.startsWith('```', i)) {
      const end = text.indexOf('```', i + 3);
      if (end > i + 3) {
        out.push({ kind: 'mono', value: text.slice(i + 3, end) });
        i = end + 3;
        continue;
      }
    }
    const kind = MARKERS[c];
    if (kind && !isWord(text[i - 1]) && !isSpace(text[i + 1]) && text[i + 1] !== c) {
      const close = findClose(text, i + 1, c);
      if (close > i + 1) {
        out.push({ kind, children: parseWhatsAppFormat(text.slice(i + 1, close)) });
        i = close + 1;
        continue;
      }
    }
    pushText(out, c);
    i++;
  }
  return out;
}
