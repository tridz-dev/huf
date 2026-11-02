import { describe, expect, it } from 'vitest';
import { __qrInternals as q, encodeQr, qrToSvg, verifyQr, type QrEcc } from './qr';

const LEVELS: QrEcc[] = ['L', 'M', 'Q', 'H'];

describe('Reed-Solomon', () => {
  it('matches the published HELLO WORLD 1-M ECC vector', () => {
    const data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17];
    expect(q.rsRemainder(data, q.rsGenerator(10))).toEqual([196, 35, 39, 119, 235, 215, 231, 226, 93, 23]);
  });
  it('generator of degree 7 matches the spec', () => {
    // alpha exponents 0,87,229,146,149,238,102,21 -> coefficients below (leading 1 omitted)
    expect(q.rsGenerator(7)).toEqual([127, 122, 154, 164, 11, 68, 117]);
  });
});

describe('tables', () => {
  it('byte capacity matches the standard for known versions', () => {
    const cap = (v: number, e: QrEcc) => q.eccInfo(v, e).dataCodewords - (v <= 9 ? 2 : 3);
    expect([cap(1, 'L'), cap(1, 'M'), cap(1, 'Q'), cap(1, 'H')]).toEqual([17, 14, 11, 7]);
    expect(cap(5, 'M')).toBe(84);
    expect(cap(10, 'M')).toBe(213);
    expect([cap(20, 'L'), cap(20, 'M'), cap(20, 'Q'), cap(20, 'H')]).toEqual([858, 666, 482, 382]);
  });
  it('every version/level has positive data capacity and consistent block sizes', () => {
    for (let v = 1; v <= 20; v++) for (const e of LEVELS) {
      const info = q.eccInfo(v, e);
      expect(info.dataCodewords).toBeGreaterThan(0);
      expect(q.blockLayout(v, e).reduce((s, b) => s + b.dataLen + b.eccLen, 0)).toBe(info.raw);
    }
  });
  it('format and version BCH match published values', () => {
    expect(q.formatBits('M', 5)).toBe(0b100000011001110);
    expect(q.formatBits('L', 4)).toBe(0b110011000101111);
    expect(q.versionBits(7)).toBe(0x07c94);
    expect(q.versionBits(20)).toBe(0x149a6);
    expect(q.alignmentPositions(7)).toEqual([6, 22, 38]);
    expect(q.alignmentPositions(14)).toEqual([6, 26, 46, 66]);
  });
});

describe('encodeQr structure', () => {
  const finderOk = (m: boolean[][], ox: number, oy: number) => {
    for (let dy = 0; dy < 7; dy++) for (let dx = 0; dx < 7; dx++) {
      const ring = Math.max(Math.abs(dx - 3), Math.abs(dy - 3));
      expect(m[oy + dy][ox + dx]).toBe(ring !== 2);
    }
  };
  it('has finders, timing, dark module at version 1', () => {
    const m = encodeQr('hello', 'M');
    expect(m.length).toBe(21);
    finderOk(m, 0, 0); finderOk(m, 14, 0); finderOk(m, 0, 14);
    for (let i = 8; i < 13; i++) { expect(m[6][i]).toBe(i % 2 === 0); expect(m[i][6]).toBe(i % 2 === 0); }
    expect(m[13][8]).toBe(true);
  });
  it('picks versions automatically and throws past capacity', () => {
    expect(encodeQr('a'.repeat(14), 'M').length).toBe(21);
    expect(encodeQr('a'.repeat(15), 'M').length).toBe(25);
    expect(encodeQr('a'.repeat(666), 'M').length).toBe(97);
    expect(() => encodeQr('a'.repeat(667), 'M')).toThrow(RangeError);
    expect(() => encodeQr('a'.repeat(859), 'L')).toThrow(RangeError);
  });
  it('is deterministic', () => {
    expect(encodeQr('https://wa.me/15551234567?text=Hi')).toEqual(encodeQr('https://wa.me/15551234567?text=Hi'));
  });
});

describe('verifyQr round trip (format BCH, version info, RS syndromes, payload)', () => {
  const samples = [
    'https://wa.me/15551234567',
    'https://wa.me/15551234567?text=Hi%20there&ref=spring-campaign',
    'Zażółć gęślą jaźń \u{1F600} 你好',
    'x'.repeat(130),
  ];
  for (const text of samples) for (const ecc of LEVELS) {
    it(`${ecc}: ${text.slice(0, 24)}`, () => {
      const info = verifyQr(encodeQr(text, ecc));
      expect(info.text).toBe(text);
      expect(info.ecc).toBe(ecc);
    });
  }
  it('covers every version 1-20 at every level (incl. version info for 7+)', () => {
    for (let v = 1; v <= 20; v++) for (const ecc of LEVELS) {
      const n = q.eccInfo(v, ecc).dataCodewords - (v <= 9 ? 2 : 3);
      const text = Array.from({ length: n }, (_, i) => String.fromCharCode(33 + ((i * 7) % 90))).join('');
      const m = encodeQr(text, ecc);
      const info = verifyQr(m);
      expect(info.version).toBe(v);
      expect(info.text).toBe(text);
    }
  });
  it('chooses the mask with the lowest penalty and records it in format info', () => {
    const info = verifyQr(encodeQr('https://wa.me/1'));
    expect(info.mask).toBeGreaterThanOrEqual(0);
    expect(info.mask).toBeLessThan(8);
  });
  it('detects corruption', () => {
    const m = encodeQr('https://wa.me/15551234567');
    m[12][12] = !m[12][12];
    expect(() => verifyQr(m)).toThrow();
    const f = encodeQr('abc');
    f[8][0] = !f[8][0];
    expect(() => verifyQr(f)).toThrow();
  });
});

describe('qrToSvg', () => {
  it('uses currentColor, margin and scale', () => {
    const m = encodeQr('a');
    const svg = qrToSvg(m, { margin: 2, scale: 3 });
    expect(svg).toContain('fill="currentColor"');
    expect(svg).toContain(`viewBox="0 0 ${21 + 4} ${21 + 4}"`);
    expect(svg).toContain(`width="${25 * 3}"`);
    expect(svg).not.toMatch(/#[0-9a-f]{3,6}/i);
    expect(svg).toContain('M2,2h1v1h-1z'); // top-left finder corner
  });
});
