/**
 * Self-contained QR Code encoder (ISO/IEC 18004), byte mode (UTF-8), versions 1-20.
 * `encodeQr` returns a square boolean matrix indexed [y][x] (true = dark module).
 * `verifyQr` re-reads a matrix (format/version info, Reed-Solomon syndromes) and returns its text.
 */

export type QrEcc = 'L' | 'M' | 'Q' | 'H';

const ECC_INDEX: Record<QrEcc, number> = { L: 0, M: 1, Q: 2, H: 3 };
/** 2-bit format-info indicator per level (L=01, M=00, Q=11, H=10). */
const ECC_FORMAT_BITS: Record<QrEcc, number> = { L: 1, M: 0, Q: 3, H: 2 };
const MIN_VERSION = 1;
const MAX_VERSION = 20;

// Index 0 = version 1. Rows are L, M, Q, H.
const ECC_CODEWORDS_PER_BLOCK = [
  [7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28],
  [10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26],
  [13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30],
  [17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28],
];
const NUM_BLOCKS = [
  [1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8],
  [1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16],
  [1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20],
  [1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25],
];

type Matrix = boolean[][];

// ---- Layout helpers -------------------------------------------------------

const sizeOf = (version: number) => version * 4 + 17;

function rawDataModules(version: number): number {
  let n = (16 * version + 128) * version + 64;
  if (version >= 2) {
    const a = Math.floor(version / 7) + 2;
    n -= (25 * a - 10) * a - 55;
    if (version >= 7) n -= 36;
  }
  return n;
}

function eccInfo(version: number, ecc: QrEcc) {
  const e = ECC_INDEX[ecc];
  const blocks = NUM_BLOCKS[e][version - 1];
  const eccLen = ECC_CODEWORDS_PER_BLOCK[e][version - 1];
  const raw = Math.floor(rawDataModules(version) / 8);
  return { blocks, eccLen, raw, dataCodewords: raw - blocks * eccLen };
}

function alignmentPositions(version: number): number[] {
  if (version === 1) return [];
  const n = Math.floor(version / 7) + 2;
  const size = sizeOf(version);
  const step = Math.ceil((version * 4 + 4) / (n * 2 - 2)) * 2;
  const pos = [6];
  for (let p = size - 7; pos.length < n; p -= step) pos.splice(1, 0, p);
  return pos;
}

const grid = (size: number): Matrix => Array.from({ length: size }, () => new Array<boolean>(size).fill(false));
const bit = (v: number, i: number) => ((v >>> i) & 1) !== 0;

/** Format info (15 bits, BCH(15,5) + mask 0x5412) for an ECC level and mask. */
function formatBits(ecc: QrEcc, mask: number): number {
  const data = (ECC_FORMAT_BITS[ecc] << 3) | mask;
  let rem = data;
  for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
  return ((data << 10) | rem) ^ 0x5412;
}

/** Version info (18 bits, BCH(18,6)) for versions >= 7. */
function versionBits(version: number): number {
  let rem = version;
  for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
  return (version << 12) | rem;
}

/** Positions of the 15 format bits: [copy1, copy2], each indexed by bit number. */
function formatCoords(size: number): [number, number][][] {
  const a: [number, number][] = [];
  for (let i = 0; i <= 5; i++) a.push([8, i]);
  a.push([8, 7], [8, 8], [7, 8]);
  for (let i = 9; i < 15; i++) a.push([14 - i, 8]);
  const b: [number, number][] = [];
  for (let i = 0; i < 8; i++) b.push([size - 1 - i, 8]);
  for (let i = 8; i < 15; i++) b.push([8, size - 15 + i]);
  return [a, b];
}

/** Draws all function patterns (format area reserved as light) and returns the function-module map. */
function drawFunctionPatterns(m: Matrix, version: number): Matrix {
  const size = m.length;
  const fn = grid(size);
  const set = (x: number, y: number, dark: boolean) => {
    m[y][x] = dark;
    fn[y][x] = true;
  };
  for (let i = 0; i < size; i++) {
    set(6, i, i % 2 === 0);
    set(i, 6, i % 2 === 0);
  }
  // Finder patterns with separators.
  for (const [cx, cy] of [[3, 3], [size - 4, 3], [3, size - 4]]) {
    for (let dy = -4; dy <= 4; dy++) {
      for (let dx = -4; dx <= 4; dx++) {
        const x = cx + dx, y = cy + dy;
        if (x < 0 || y < 0 || x >= size || y >= size) continue;
        set(x, y, Math.max(Math.abs(dx), Math.abs(dy)) !== 4 && Math.max(Math.abs(dx), Math.abs(dy)) !== 2);
      }
    }
  }
  // Alignment patterns (skipping those overlapping finders).
  const ap = alignmentPositions(version);
  for (let i = 0; i < ap.length; i++) {
    for (let j = 0; j < ap.length; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === ap.length - 1) || (i === ap.length - 1 && j === 0)) continue;
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) set(ap[i] + dx, ap[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
      }
    }
  }
  for (const copy of formatCoords(size)) for (const [x, y] of copy) set(x, y, false);
  set(8, size - 8, true); // dark module
  if (version >= 7) {
    const bits = versionBits(version);
    for (let i = 0; i < 18; i++) {
      const a = size - 11 + (i % 3), b = Math.floor(i / 3);
      set(a, b, bit(bits, i));
      set(b, a, bit(bits, i));
    }
  }
  return fn;
}

function drawFormat(m: Matrix, ecc: QrEcc, mask: number) {
  const bits = formatBits(ecc, mask);
  for (const copy of formatCoords(m.length)) copy.forEach(([x, y], i) => { m[y][x] = bit(bits, i); });
  m[m.length - 8][8] = true;
}

/** Zigzag module order for codeword placement, skipping function modules. */
function dataCoords(fn: Matrix): [number, number][] {
  const size = fn.length;
  const out: [number, number][] = [];
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vert = 0; vert < size; vert++) {
      for (let j = 0; j < 2; j++) {
        const x = right - j;
        const y = ((right + 1) & 2) === 0 ? size - 1 - vert : vert;
        if (!fn[y][x]) out.push([x, y]);
      }
    }
  }
  return out;
}

const MASKS: ((x: number, y: number) => boolean)[] = [
  (x, y) => (x + y) % 2 === 0,
  (_x, y) => y % 2 === 0,
  (x) => x % 3 === 0,
  (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
  (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
  (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
  (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
];

// ---- Reed-Solomon over GF(256), polynomial 0x11D --------------------------

const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);
for (let i = 0, x = 1; i < 255; i++) {
  EXP[i] = x;
  LOG[x] = i;
  x <<= 1;
  if (x & 0x100) x ^= 0x11d;
}
for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];

const gfMul = (a: number, b: number) => (a === 0 || b === 0 ? 0 : EXP[LOG[a] + LOG[b]]);

/** Generator polynomial of the given degree (highest-order coefficient first, leading 1 omitted). */
function rsGenerator(degree: number): number[] {
  const g = new Array<number>(degree).fill(0);
  g[degree - 1] = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < degree; j++) {
      g[j] = gfMul(g[j], EXP[i]);
      if (j + 1 < degree) g[j] ^= g[j + 1];
    }
  }
  return g;
}

function rsRemainder(data: number[], gen: number[]): number[] {
  const rem = new Array<number>(gen.length).fill(0);
  for (const b of data) {
    const factor = b ^ (rem.shift() as number);
    rem.push(0);
    gen.forEach((c, i) => { rem[i] ^= gfMul(c, factor); });
  }
  return rem;
}

/** Evaluate the codeword polynomial at alpha^i (syndrome); zero for a valid codeword. */
function rsSyndrome(codeword: number[], i: number): number {
  let acc = 0;
  for (const c of codeword) acc = gfMul(acc, EXP[i]) ^ c;
  return acc;
}

/** Block layout: data/ecc lengths for each block, in order. */
function blockLayout(version: number, ecc: QrEcc) {
  const { blocks, eccLen, raw } = eccInfo(version, ecc);
  const numShort = blocks - (raw % blocks);
  const shortLen = Math.floor(raw / blocks);
  return Array.from({ length: blocks }, (_, i) => ({ dataLen: shortLen - eccLen + (i < numShort ? 0 : 1), eccLen }));
}

// ---- Encoding -------------------------------------------------------------

function utf8(text: string): number[] {
  return Array.from(new TextEncoder().encode(text));
}

function penalty(m: Matrix): number {
  const size = m.length;
  let score = 0;
  const FINDER_A = '10111010000', FINDER_B = '00001011101';
  for (let pass = 0; pass < 2; pass++) {
    for (let a = 0; a < size; a++) {
      let line = '';
      let run = 1;
      for (let b = 0; b < size; b++) {
        const v = pass === 0 ? m[a][b] : m[b][a];
        line += v ? '1' : '0';
        if (b > 0) {
          const prev = pass === 0 ? m[a][b - 1] : m[b - 1][a];
          if (v === prev) run++;
          else { if (run >= 5) score += 3 + run - 5; run = 1; }
        }
      }
      if (run >= 5) score += 3 + run - 5;
      for (let i = 0; i + 11 <= size; i++) {
        const s = line.substr(i, 11);
        if (s === FINDER_A || s === FINDER_B) score += 40;
      }
    }
  }
  let dark = 0;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      if (m[y][x]) dark++;
      if (x + 1 < size && y + 1 < size && m[y][x] === m[y][x + 1] && m[y][x] === m[y + 1][x] && m[y][x] === m[y + 1][x + 1]) score += 3;
    }
  }
  const total = size * size;
  score += (Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1) * 10;
  return score;
}

export function encodeQr(text: string, ecc: QrEcc = 'M'): boolean[][] {
  const bytes = utf8(text);
  let version = MIN_VERSION;
  for (;; version++) {
    if (version > MAX_VERSION) throw new RangeError('Text is too long for a QR code (max version 20)');
    const countBits = version <= 9 ? 8 : 16;
    if (4 + countBits + bytes.length * 8 <= eccInfo(version, ecc).dataCodewords * 8 && bytes.length < 1 << countBits) break;
  }
  const { dataCodewords, raw } = eccInfo(version, ecc);

  // Bit stream: mode 0100, count, data, terminator, byte alignment, pad bytes.
  const bits: number[] = [];
  const push = (value: number, len: number) => { for (let i = len - 1; i >= 0; i--) bits.push((value >>> i) & 1); };
  push(0b0100, 4);
  push(bytes.length, version <= 9 ? 8 : 16);
  bytes.forEach((b) => push(b, 8));
  push(0, Math.min(4, dataCodewords * 8 - bits.length));
  push(0, (8 - (bits.length % 8)) % 8);
  const data: number[] = [];
  for (let i = 0; i < bits.length; i += 8) data.push(parseInt(bits.slice(i, i + 8).join(''), 2));
  for (let pad = 0xec; data.length < dataCodewords; pad ^= 0xec ^ 0x11) data.push(pad);

  // Split into blocks, append RS ECC, interleave.
  const layout = blockLayout(version, ecc);
  const gen = rsGenerator(layout[0].eccLen);
  const dataBlocks: number[][] = [];
  const eccBlocks: number[][] = [];
  let off = 0;
  for (const { dataLen } of layout) {
    const d = data.slice(off, off + dataLen);
    off += dataLen;
    dataBlocks.push(d);
    eccBlocks.push(rsRemainder(d, gen));
  }
  const codewords: number[] = [];
  const maxData = Math.max(...layout.map((l) => l.dataLen));
  for (let i = 0; i < maxData; i++) for (const d of dataBlocks) if (i < d.length) codewords.push(d[i]);
  for (let i = 0; i < layout[0].eccLen; i++) for (const e of eccBlocks) codewords.push(e[i]);
  if (codewords.length !== raw) throw new Error('QR codeword count mismatch');

  // Place modules.
  const size = sizeOf(version);
  const base = grid(size);
  const fn = drawFunctionPatterns(base, version);
  dataCoords(fn).forEach(([x, y], i) => {
    if (i < codewords.length * 8) base[y][x] = bit(codewords[i >> 3], 7 - (i & 7));
  });

  let best: Matrix | null = null;
  let bestScore = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    const m = base.map((row) => row.slice());
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) if (!fn[y][x] && MASKS[mask](x, y)) m[y][x] = !m[y][x];
    drawFormat(m, ecc, mask);
    const score = penalty(m);
    if (score < bestScore) { bestScore = score; best = m; }
  }
  return best as Matrix;
}

// ---- Verification ----------------------------------------------------------

export interface QrInfo { version: number; ecc: QrEcc; mask: number; text: string }

/** Decoder-free self-check: validates format/version info and RS syndromes; returns the embedded text. Throws on any inconsistency. */
export function verifyQr(matrix: boolean[][]): QrInfo {
  const size = matrix.length;
  if (size < 21 || (size - 17) % 4 !== 0 || matrix.some((r) => r.length !== size)) throw new Error('Bad matrix size');
  const version = (size - 17) / 4;
  if (version > MAX_VERSION) throw new Error('Unsupported version');

  const [c1, c2] = formatCoords(size);
  const read = (coords: [number, number][]) => coords.reduce((acc, [x, y], i) => acc | ((matrix[y][x] ? 1 : 0) << i), 0);
  const f1 = read(c1);
  if (f1 !== read(c2)) throw new Error('Format copies differ');
  let found: { ecc: QrEcc; mask: number } | null = null;
  for (const ecc of ['L', 'M', 'Q', 'H'] as QrEcc[]) {
    for (let mask = 0; mask < 8; mask++) if (formatBits(ecc, mask) === f1) found = { ecc, mask };
  }
  if (!found) throw new Error('Invalid format information');
  if (!matrix[size - 8][8]) throw new Error('Dark module missing');
  if (version >= 7) {
    const vb = versionBits(version);
    for (let i = 0; i < 18; i++) {
      const a = size - 11 + (i % 3), b = Math.floor(i / 3);
      if (matrix[b][a] !== bit(vb, i) || matrix[a][b] !== bit(vb, i)) throw new Error('Invalid version information');
    }
  }

  const fn = drawFunctionPatterns(grid(size), version);
  const coords = dataCoords(fn);
  const { raw } = eccInfo(version, found.ecc);
  const codewords: number[] = [];
  for (let i = 0; i < raw * 8; i++) {
    const [x, y] = coords[i];
    const v = matrix[y][x] !== MASKS[found.mask](x, y);
    if (i % 8 === 0) codewords.push(0);
    codewords[i >> 3] = (codewords[i >> 3] << 1) | (v ? 1 : 0);
  }

  // De-interleave and check syndromes.
  const layout = blockLayout(version, found.ecc);
  const blocks: number[][] = layout.map(() => []);
  let k = 0;
  const maxData = Math.max(...layout.map((l) => l.dataLen));
  for (let i = 0; i < maxData; i++) layout.forEach((l, b) => { if (i < l.dataLen) blocks[b].push(codewords[k++]); });
  for (let i = 0; i < layout[0].eccLen; i++) blocks.forEach((blk) => blk.push(codewords[k++]));
  blocks.forEach((blk, b) => {
    for (let i = 0; i < layout[b].eccLen; i++) if (rsSyndrome(blk, i) !== 0) throw new Error(`RS syndrome nonzero in block ${b}`);
  });

  // Parse byte-mode payload.
  const data = blocks.flatMap((blk, b) => blk.slice(0, layout[b].dataLen));
  const stream = data.map((c) => c.toString(2).padStart(8, '0')).join('');
  if (stream.slice(0, 4) !== '0100') throw new Error('Not byte mode');
  const countBits = version <= 9 ? 8 : 16;
  const count = parseInt(stream.slice(4, 4 + countBits), 2);
  const out: number[] = [];
  for (let i = 0; i < count; i++) out.push(parseInt(stream.slice(4 + countBits + i * 8, 12 + countBits + i * 8), 2));
  return { version, ecc: found.ecc, mask: found.mask, text: new TextDecoder().decode(new Uint8Array(out)) };
}

// ---- SVG -------------------------------------------------------------------

export function qrToSvg(matrix: boolean[][], { margin = 4, scale = 4 }: { margin?: number; scale?: number } = {}): string {
  const n = matrix.length + margin * 2;
  let d = '';
  matrix.forEach((row, y) => row.forEach((dark, x) => { if (dark) d += `M${x + margin},${y + margin}h1v1h-1z`; }));
  const px = n * scale;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n} ${n}" width="${px}" height="${px}" shape-rendering="crispEdges" role="img"><path d="${d}" fill="currentColor"/></svg>`;
}

/** Exposed for tests only. */
export const __qrInternals = { rsGenerator, rsRemainder, eccInfo, blockLayout, formatBits, versionBits, alignmentPositions };
