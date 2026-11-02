/**
 * Plain-language problems for text that should be JSON (UX-2 JsonArea): where it is wrong and what to do,
 * never the parser's own wording ("Unexpected token } in JSON at position 41").
 */

export interface JsonProblem {
  /** 1-based line the problem is on. */
  line: number;
  /** Sentence shown under the box, e.g. "Missing comma after line 3." */
  message: string;
}

const lineAt = (text: string, pos: number): number => text.slice(0, Math.max(0, Math.min(pos, text.length))).split('\n').length;

/** Index of the last non-space character before `pos`, or -1. */
function prevSignificant(text: string, pos: number): number {
  for (let i = Math.min(pos, text.length) - 1; i >= 0; i--) if (!/\s/.test(text[i])) return i;
  return -1;
}

function positionOf(error: unknown, text: string): number {
  const msg = error instanceof Error ? error.message : String(error);
  const at = /position (\d+)/.exec(msg);
  if (at) return Number(at[1]);
  const lc = /line (\d+) column (\d+)/.exec(msg);
  if (lc) {
    const lines = text.split('\n');
    const line = Number(lc[1]);
    return lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0) + Number(lc[2]) - 1;
  }
  return text.length;
}

/** `null` when `text` is valid JSON (an empty box is the caller's call), else the first problem in plain words. */
export function describeJsonProblem(text: string): JsonProblem | null {
  try {
    JSON.parse(text);
    return null;
  } catch (error) {
    const pos = positionOf(error, text);
    const prev = prevSignificant(text, pos);
    const here = text[pos];
    if (pos >= text.length || (prev >= 0 && pos >= text.length - 1 && /\s/.test(here ?? ' '))) {
      return { line: lineAt(text, text.length), message: 'The text stops too early: a closing } or ] is missing at the end.' };
    }
    if (text[prev] === ',' && (here === '}' || here === ']')) {
      return { line: lineAt(text, prev), message: `Remove the extra comma at the end of line ${lineAt(text, prev)}.` };
    }
    if (here === "'" || text[prev] === "'") {
      return { line: lineAt(text, pos), message: `Use double quotes (") around names and text on line ${lineAt(text, pos)}.` };
    }
    if (prev >= 0 && /["\]}0-9el]/.test(text[prev]) && (here === '"' || /[{[\d-]/.test(here) || /[tfn]/.test(here))) {
      return { line: lineAt(text, prev), message: `Missing comma after line ${lineAt(text, prev)}.` };
    }
    if (text[prev] === ':' || here === ':') {
      return { line: lineAt(text, pos), message: `A name or value is missing around the colon on line ${lineAt(text, pos)}.` };
    }
    return { line: lineAt(text, pos), message: `Something on line ${lineAt(text, pos)} is not valid. Check the quotes, commas and brackets there.` };
  }
}

/** Pretty-printed form of valid JSON text, or null when it cannot be parsed. */
export function formatJsonText(text: string): string | null {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return null;
  }
}
