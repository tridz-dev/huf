import { describe, it, expect } from 'vitest';
import {
  computeBackoffDelayMs,
  chunkRecordId,
  blobToBase64,
  MAX_AUTO_RETRIES,
  DEFAULT_TIMESLICE_MS,
} from './useMeetingRecorder';

describe('computeBackoffDelayMs', () => {
  it('doubles the delay for each retry, starting at 2s', () => {
    expect(computeBackoffDelayMs(0)).toBe(2_000);
    expect(computeBackoffDelayMs(1)).toBe(4_000);
    expect(computeBackoffDelayMs(2)).toBe(8_000);
    expect(computeBackoffDelayMs(3)).toBe(16_000);
  });

  it('caps the delay at 60s', () => {
    expect(computeBackoffDelayMs(10)).toBe(60_000);
    expect(computeBackoffDelayMs(MAX_AUTO_RETRIES)).toBeLessThanOrEqual(60_000);
  });

  it('treats negative retry counts as the first attempt', () => {
    expect(computeBackoffDelayMs(-1)).toBe(2_000);
  });
});

describe('chunkRecordId', () => {
  it('builds a stable, sortable-by-meeting key from meeting + sequence', () => {
    expect(chunkRecordId('MEETING-001', 0)).toBe('MEETING-001:0');
    expect(chunkRecordId('MEETING-001', 12)).toBe('MEETING-001:12');
  });

  it('produces distinct keys for different meetings with the same sequence', () => {
    expect(chunkRecordId('MEETING-001', 3)).not.toBe(chunkRecordId('MEETING-002', 3));
  });
});

describe('blobToBase64', () => {
  it('round-trips small binary content to base64', async () => {
    const bytes = new Uint8Array([104, 101, 108, 108, 111]); // "hello"
    const blob = new Blob([bytes], { type: 'audio/webm' });
    const b64 = await blobToBase64(blob);
    expect(b64).toBe(Buffer.from(bytes).toString('base64'));
  });

  it('handles an empty blob', async () => {
    const blob = new Blob([], { type: 'audio/webm' });
    const b64 = await blobToBase64(blob);
    expect(b64).toBe('');
  });
});

describe('constants', () => {
  it('keeps the default segment length within the 30-60s target window', () => {
    expect(DEFAULT_TIMESLICE_MS).toBeGreaterThanOrEqual(30_000);
    expect(DEFAULT_TIMESLICE_MS).toBeLessThanOrEqual(60_000);
  });
});
