/**
 * Small self-contained word-level diff between two response texts.
 *
 * Tokenizes on whitespace boundaries (keeping the whitespace tokens so the
 * original text can be reassembled verbatim), then runs an LCS over the token
 * sequences. Tokens outside the LCS are marked `added` (present in B only) or
 * `removed` (present in A only) on their respective side.
 */

export type DiffSegmentType = 'unchanged' | 'added' | 'removed';

export interface DiffSegment {
  text: string;
  type: DiffSegmentType;
}

export interface WordDiff {
  a: DiffSegment[];
  b: DiffSegment[];
}

/** Above this many tokens per side, LCS gets expensive — mark everything changed. */
const MAX_TOKENS = 1200;

function tokenize(text: string): string[] {
  return text.split(/(\s+)/).filter((t) => t.length > 0);
}

function pushSegment(segments: DiffSegment[], text: string, type: DiffSegmentType) {
  if (!text) return;
  const last = segments[segments.length - 1];
  if (last && last.type === type) {
    last.text += text;
  } else {
    segments.push({ text, type });
  }
}

export function wordDiff(textA: string, textB: string): WordDiff {
  const tokensA = tokenize(textA);
  const tokensB = tokenize(textB);

  if (tokensA.length > MAX_TOKENS || tokensB.length > MAX_TOKENS) {
    return {
      a: [{ text: textA, type: 'removed' }],
      b: [{ text: textB, type: 'added' }],
    };
  }

  const rows = tokensA.length;
  const cols = tokensB.length;
  // lengths[i][j] stored flat: LCS length of tokensA[i:] and tokensB[j:].
  const lengths = new Uint32Array((rows + 1) * (cols + 1));
  const stride = cols + 1;

  for (let i = rows - 1; i >= 0; i--) {
    for (let j = cols - 1; j >= 0; j--) {
      lengths[i * stride + j] =
        tokensA[i] === tokensB[j]
          ? lengths[(i + 1) * stride + (j + 1)] + 1
          : Math.max(lengths[(i + 1) * stride + j], lengths[i * stride + (j + 1)]);
    }
  }

  const a: DiffSegment[] = [];
  const b: DiffSegment[] = [];
  let i = 0;
  let j = 0;
  while (i < rows && j < cols) {
    if (tokensA[i] === tokensB[j]) {
      pushSegment(a, tokensA[i], 'unchanged');
      pushSegment(b, tokensB[j], 'unchanged');
      i++;
      j++;
    } else if (lengths[(i + 1) * stride + j] >= lengths[i * stride + (j + 1)]) {
      pushSegment(a, tokensA[i], 'removed');
      i++;
    } else {
      pushSegment(b, tokensB[j], 'added');
      j++;
    }
  }
  while (i < rows) pushSegment(a, tokensA[i++], 'removed');
  while (j < cols) pushSegment(b, tokensB[j++], 'added');

  return { a, b };
}
