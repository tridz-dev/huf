// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { validateInteractive, validateMediaSend, validateVoiceNote, type InteractiveKind } from '@/services/whatsappApi';
import {
  contactSchema, interactiveSchema, locationSchema, mediaSchema, reactionSchema, textSchema, MSG,
} from './sendSchemas';

const msgs = (r: { success: boolean; error?: { issues: { message: string }[] } }) => (r.success ? [] : r.error!.issues.map((i) => i.message));
const media = { link: '', file: null, caption: '', voice: false };

describe('textSchema', () => {
  it('needs non-blank text', () => {
    expect(textSchema.safeParse({ text: 'hi' }).success).toBe(true);
    expect(msgs(textSchema.safeParse({ text: '   ' }))).toEqual([MSG.text]);
  });
});

describe('mediaSchema', () => {
  it('needs a link or file', () => {
    expect(msgs(mediaSchema('image').safeParse(media))).toEqual([MSG.noSource]);
    expect(mediaSchema('image').safeParse({ ...media, file: { fileUrl: '/f', name: 'a.png' } }).success).toBe(true);
  });
  it('requires https and caps the caption', () => {
    expect(msgs(mediaSchema('image').safeParse({ ...media, link: 'http://x.io/a.png' }))).toEqual([MSG.https]);
    expect(msgs(mediaSchema('image').safeParse({ ...media, link: 'https://x.io/a.png', caption: 'x'.repeat(1025) }))).toEqual([MSG.caption]);
    expect(mediaSchema('image').safeParse({ ...media, link: 'https://x.io/a.png', caption: 'x'.repeat(1024) }).success).toBe(true);
  });
  it('audio cannot have a caption', () => {
    expect(msgs(mediaSchema('audio').safeParse({ ...media, link: 'https://x.io/a.mp3', caption: 'c' }))).toEqual([MSG.audioCaption]);
  });
  it('sticker only needs a source (no https check)', () => {
    expect(mediaSchema('sticker').safeParse({ ...media, link: 'http://x.io/s.webp' }).success).toBe(true);
    expect(msgs(mediaSchema('sticker').safeParse(media))).toEqual([MSG.noSource]);
  });
  it('voice note needs an ogg/opus link or file name', () => {
    const s = mediaSchema('audio');
    expect(msgs(s.safeParse({ ...media, voice: true, link: 'https://x.io/a.mp3' }))).toEqual([MSG.voice]);
    expect(s.safeParse({ ...media, voice: true, link: 'https://x.io/a.OGG?x=1' }).success).toBe(true);
    expect(s.safeParse({ ...media, voice: true, file: { fileUrl: '/f/1', name: 'v.opus' } }).success).toBe(true);
    expect(msgs(s.safeParse({ ...media, voice: true, file: { fileUrl: '/f/1', name: 'v.mp3' } }))).toEqual([MSG.voice]);
  });
  it('agrees with validateMediaSend / validateVoiceNote', () => {
    const cases = [
      { link: '', file: null, caption: '' }, { link: 'http://a', file: null, caption: '' }, { link: 'https://a', file: null, caption: 'c' },
      { link: 'https://a', file: null, caption: 'x'.repeat(1025) }, { link: '', file: { fileUrl: '/f', name: 'n.ogg' }, caption: '' },
    ];
    for (const kind of ['image', 'audio', 'document', 'video'] as const) {
      for (const c of cases) {
        const expected = validateMediaSend({ kind, link: c.link, fileUrl: c.file?.fileUrl, caption: c.caption });
        expect(msgs(mediaSchema(kind).safeParse({ ...c, voice: false }))[0] ?? null).toBe(expected);
      }
    }
    for (const c of cases) {
      const expected = validateVoiceNote({ link: c.link, fileUrl: c.file?.fileUrl, fileName: c.file?.name });
      expect(msgs(mediaSchema('audio').safeParse({ ...c, voice: true }))[0] ?? null).toBe(expected);
    }
  });
});

describe('locationSchema', () => {
  const ok = { lat: '12.5', lng: '-77', name: '', address: '' };
  it('accepts a valid position', () => expect(locationSchema.safeParse(ok).success).toBe(true));
  it('needs numeric latitude and longitude', () => {
    expect(msgs(locationSchema.safeParse({ ...ok, lat: '', lng: '' }))).toEqual([MSG.latLng, MSG.latLng]);
    expect(msgs(locationSchema.safeParse({ ...ok, lat: 'abc' }))).toEqual([MSG.latLng]);
  });
  it('enforces ranges at the boundary', () => {
    expect(locationSchema.safeParse({ ...ok, lat: '90', lng: '180' }).success).toBe(true);
    expect(msgs(locationSchema.safeParse({ ...ok, lat: '90.1' }))).toEqual([MSG.latLngRange]);
    expect(msgs(locationSchema.safeParse({ ...ok, lng: '-180.5' }))).toEqual([MSG.latLngRange]);
  });
});

describe('contactSchema', () => {
  const base = { name: 'Ann', phone: '', email: '', org: '' };
  it('needs a name', () => expect(msgs(contactSchema.safeParse({ ...base, name: ' ', phone: '1' }))).toEqual([MSG.contactName]));
  it('needs a phone or an email', () => {
    expect(msgs(contactSchema.safeParse(base))).toEqual([MSG.contactReach]);
    expect(contactSchema.safeParse({ ...base, email: 'a@b.co' }).success).toBe(true);
  });
});

describe('reactionSchema', () => {
  it('needs a message id; an emoji only when adding', () => {
    expect(msgs(reactionSchema.safeParse({ messageId: ' ', emoji: '', remove: false }))).toEqual([MSG.messageId, MSG.emoji]);
    expect(msgs(reactionSchema.safeParse({ messageId: 'w', emoji: '', remove: false }))).toEqual([MSG.emoji]);
    expect(reactionSchema.safeParse({ messageId: 'w', emoji: '', remove: true }).success).toBe(true);
  });
});

describe('interactiveSchema', () => {
  const base = { header: '', body: 'Hi', footer: '', buttonText: '', displayText: '', url: '', buttons: [{ id: 'btn_1', title: 'Yes' }], rows: [{ title: 'A', description: '' }] };
  it('requires a body', () => expect(msgs(interactiveSchema('buttons').safeParse({ ...base, body: ' ' }))).toEqual([MSG.body]));
  it('buttons: label required, max 3, 20 chars', () => {
    const s = interactiveSchema('buttons');
    expect(msgs(s.safeParse({ ...base, buttons: [{ id: 'a', title: ' ' }] }))).toEqual([MSG.buttonLabel]);
    expect(msgs(s.safeParse({ ...base, buttons: Array.from({ length: 4 }, (_, i) => ({ id: `${i}`, title: 't' })) }))).toEqual([MSG.tooManyButtons]);
    expect(msgs(s.safeParse({ ...base, buttons: [{ id: 'a', title: 'x'.repeat(21) }] }))).toEqual([MSG.buttonLong]);
    expect(msgs(s.safeParse({ ...base, buttons: [] }))).toEqual([MSG.noButtons]);
  });
  it('list: label, item title and counts', () => {
    const s = interactiveSchema('list');
    expect(msgs(s.safeParse({ ...base }))).toEqual([MSG.listLabel]);
    expect(s.safeParse({ ...base, buttonText: 'Go' }).success).toBe(true);
    expect(msgs(s.safeParse({ ...base, buttonText: 'Go', rows: [{ title: 'x'.repeat(25), description: '' }] }))).toEqual([MSG.rowTitle]);
    expect(msgs(s.safeParse({ ...base, buttonText: 'Go', rows: Array.from({ length: 11 }, () => ({ title: 'a', description: '' })) }))).toEqual([MSG.tooManyRows]);
    expect(msgs(s.safeParse({ ...base, buttonText: 'Go', rows: [] }))).toEqual([MSG.noRows]);
  });
  it('cta_url: label and https link', () => {
    const s = interactiveSchema('cta_url');
    expect(msgs(s.safeParse({ ...base, url: 'http://a' }))).toEqual([MSG.ctaLabel, MSG.https]);
    expect(s.safeParse({ ...base, displayText: 'Open', url: ' https://a.io ' }).success).toBe(true);
  });
  it('agrees with validateInteractive', () => {
    const variants = [
      base, { ...base, body: '' }, { ...base, buttonText: 'Go' }, { ...base, displayText: 'Open', url: 'https://a.io' },
      { ...base, displayText: 'Open', url: 'http://a.io' }, { ...base, buttons: [{ id: 'a', title: '' }] },
    ];
    for (const kind of ['buttons', 'list', 'cta_url'] as InteractiveKind[]) {
      for (const v of variants) {
        const expected = validateInteractive({
          kind, body: v.body, header: v.header, footer: v.footer, buttonText: v.buttonText, displayText: v.displayText, url: v.url,
          buttons: v.buttons, sections: [{ title: 'Options', rows: v.rows.map((r, i) => ({ id: `row_${i + 1}`, title: r.title })) }],
        });
        expect(interactiveSchema(kind).safeParse(v).success).toBe(expected === null);
      }
    }
  });
});
