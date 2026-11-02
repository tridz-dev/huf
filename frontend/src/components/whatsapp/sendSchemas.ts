import { z } from 'zod';
import { INTERACTIVE_LIMITS, type InteractiveKind, type MediaKind } from '@/services/whatsappApi';

/**
 * Zod schemas for the WhatsApp send forms (one per send type). The rules and
 * messages are the ones `validateMediaSend`, `validateVoiceNote` and
 * `validateInteractive` (services/whatsappApi) enforce; the forms in
 * SendForms.tsx resolve through these. The recipient ("To") lives in
 * SendPanel and gates every Send button, so it is not part of these schemas.
 * Template sends are handled by TemplateSend, not here.
 */

const HTTPS = /^https:\/\//;
const VOICE_EXT = /\.(ogg|opus|oga)$/i;

export const MSG = {
  noSource: 'Add a file or paste a public link',
  https: 'The link must start with https://',
  audioCaption: 'Audio messages cannot have a caption',
  caption: 'Caption is limited to 1024 characters',
  voice: 'A voice note must be an Ogg file with the Opus codec (.ogg or .opus)',
  latLng: 'Enter a latitude and longitude',
  latLngRange: 'Latitude is between -90 and 90, longitude between -180 and 180',
  contactName: 'Add the contact name',
  contactReach: 'Add a phone number or an email',
  messageId: 'Add the ID of the message to react to',
  emoji: 'Add an emoji',
  text: 'Type a message',
  body: 'Add the message text',
  noButtons: 'Add at least one button',
  tooManyButtons: 'Use at most 3 buttons',
  buttonLabel: 'Every button needs a label',
  buttonLong: 'Button labels are limited to 20 characters',
  listLabel: 'Add the label for the list button',
  noRows: 'Add at least one list item',
  tooManyRows: 'A list can have at most 10 items',
  rowTitle: 'List item titles are required and limited to 24 characters',
  ctaLabel: 'Add the button label',
} as const;

/* ---------------------------------- text --------------------------------- */

export const textSchema = z.object({
  text: z.string().refine((v) => v.trim().length > 0, MSG.text),
});
export type TextValues = z.infer<typeof textSchema>;

/* ------------------------------ media / sticker -------------------------- */

const uploadedFile = z.object({ fileUrl: z.string(), name: z.string() }).nullable();

export type SendMediaKind = MediaKind | 'sticker';

const mediaShape = {
  link: z.string(),
  file: uploadedFile,
  caption: z.string(),
  voice: z.boolean(),
};

/**
 * Media, sticker and voice-note sends. First problem wins, as before:
 * stickers only need a source (no https check); voice notes (audio with the
 * voice box ticked) need an Ogg/Opus file; everything else follows
 * `validateMediaSend`.
 */
export function mediaSchema(kind: SendMediaKind) {
  return z.object(mediaShape).superRefine((v, ctx) => {
    const link = v.link.trim();
    const add = (path: string, message: string) => ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
    if (!link && !v.file) return add('link', MSG.noSource);
    if (kind === 'sticker') return;
    if (link && !HTTPS.test(link)) return add('link', MSG.https);
    if (kind === 'audio' && v.voice) {
      const target = (link ? link.split(/[?#]/)[0] : v.file?.name || v.file?.fileUrl || '').trim();
      if (!VOICE_EXT.test(target)) add(link ? 'link' : 'file', MSG.voice);
      return;
    }
    if (kind === 'audio' && v.caption.trim()) return add('caption', MSG.audioCaption);
    if (v.caption.length > 1024) add('caption', MSG.caption);
  });
}
export type MediaValues = z.infer<ReturnType<typeof mediaSchema>>;

/* -------------------------------- location ------------------------------- */

export const locationSchema = z.object({
  lat: z.string(),
  lng: z.string(),
  name: z.string(),
  address: z.string(),
}).superRefine((v, ctx) => {
  const latitude = Number(v.lat);
  const longitude = Number(v.lng);
  const add = (path: string, message: string) => ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
  const latBad = !v.lat.trim() || Number.isNaN(latitude);
  const lngBad = !v.lng.trim() || Number.isNaN(longitude);
  if (latBad) add('lat', MSG.latLng);
  if (lngBad) add('lng', MSG.latLng);
  if (latBad || lngBad) return;
  if (Math.abs(latitude) > 90) add('lat', MSG.latLngRange);
  if (Math.abs(longitude) > 180) add('lng', MSG.latLngRange);
});
export type LocationValues = z.infer<typeof locationSchema>;

/* --------------------------------- contact ------------------------------- */

export const contactSchema = z.object({
  name: z.string().refine((v) => v.trim().length > 0, MSG.contactName),
  phone: z.string(),
  email: z.string(),
  org: z.string(),
}).superRefine((v, ctx) => {
  if (!v.phone.trim() && !v.email.trim()) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['phone'], message: MSG.contactReach });
  }
});
export type ContactValues = z.infer<typeof contactSchema>;

/* -------------------------------- reaction ------------------------------- */

/** `remove` is set by the Remove button before submit; an emoji is only needed to add. */
export const reactionSchema = z.object({
  messageId: z.string().refine((v) => v.trim().length > 0, MSG.messageId),
  emoji: z.string(),
  remove: z.boolean(),
}).superRefine((v, ctx) => {
  if (!v.remove && !v.emoji.trim()) ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['emoji'], message: MSG.emoji });
});
export type ReactionValues = z.infer<typeof reactionSchema>;

/* ------------------------------- interactive ----------------------------- */

export const interactiveSchema = (kind: InteractiveKind) => z.object({
  header: z.string(),
  body: z.string(),
  footer: z.string(),
  buttons: z.array(z.object({ id: z.string(), title: z.string() })),
  buttonText: z.string(),
  rows: z.array(z.object({ title: z.string(), description: z.string() })),
  displayText: z.string(),
  url: z.string(),
}).superRefine((v, ctx) => {
  const add = (path: (string | number)[], message: string) => ctx.addIssue({ code: z.ZodIssueCode.custom, path, message });
  if (!v.body.trim()) add(['body'], MSG.body);
  if (kind === 'buttons') {
    if (v.buttons.length < 1) add(['buttons'], MSG.noButtons);
    if (v.buttons.length > INTERACTIVE_LIMITS.buttons) add(['buttons'], MSG.tooManyButtons);
    v.buttons.forEach((b, i) => {
      if (!b.title.trim()) add(['buttons', i, 'title'], MSG.buttonLabel);
      else if (b.title.length > INTERACTIVE_LIMITS.buttonTitle) add(['buttons', i, 'title'], MSG.buttonLong);
    });
  } else if (kind === 'list') {
    if (!v.buttonText.trim()) add(['buttonText'], MSG.listLabel);
    if (v.rows.length < 1) add(['rows'], MSG.noRows);
    if (v.rows.length > INTERACTIVE_LIMITS.listRows) add(['rows'], MSG.tooManyRows);
    v.rows.forEach((r, i) => {
      if (!r.title.trim() || r.title.length > INTERACTIVE_LIMITS.rowTitle) add(['rows', i, 'title'], MSG.rowTitle);
    });
  } else {
    if (!v.displayText.trim()) add(['displayText'], MSG.ctaLabel);
    if (!HTTPS.test(v.url.trim())) add(['url'], MSG.https);
  }
});
export type InteractiveValues = z.infer<ReturnType<typeof interactiveSchema>>;

/** Every send type that has a schema here (template sends use TemplateSend). */
export const SEND_SCHEMAS = {
  text: textSchema,
  media: mediaSchema,
  location: locationSchema,
  contact: contactSchema,
  reaction: reactionSchema,
  interactive: interactiveSchema,
} as const;
