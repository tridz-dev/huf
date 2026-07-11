/**
 * Pure, framework-free video detection + normalization helpers.
 *
 * These are intentionally dependency-free (no React, no DOM) so they can be
 * unit-tested in a plain node environment.
 */

export const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.ogv', '.mov', '.m4v'] as const;

/** True iff the mediaType starts with "video/" (case-insensitive). */
export function isVideoMediaType(mediaType?: string | null): boolean {
  if (!mediaType) return false;
  return mediaType.toLowerCase().startsWith('video/');
}

/**
 * True iff the URL points at a known video extension.
 * Strips query/hash and lowercases before testing. Does NOT match merely
 * because the string contains the word "video" or "media".
 */
export function isVideoUrl(url?: string | null): boolean {
  if (!url) return false;
  const stripped = url.split(/[?#]/)[0].toLowerCase();
  return VIDEO_EXTENSIONS.some((ext) => stripped.endsWith(ext));
}

export type VideoPartInput = {
  type?: string; // explicit part type, e.g. "video"
  mediaType?: string; // MIME
  category?: string; // explicit attachment category e.g. "video"
  url?: string;
  src?: string;
  name?: string; // filename
};

/**
 * Detect whether an arbitrary part represents a video.
 * Priority: 1) type === 'video'  2) video mediaType  3) category === 'video'
 * 4) video extension on url/src/name.
 */
export function detectVideo(input: VideoPartInput): boolean {
  if (input.type === 'video') return true;
  if (isVideoMediaType(input.mediaType)) return true;
  if (input.category === 'video') return true;
  if (isVideoUrl(input.url ?? input.src ?? input.name)) return true;
  return false;
}

export type NormalizedVideo = {
  src: string;
  title?: string;
  poster?: string;
  mediaType?: string;
  downloadName?: string;
  captions?: Array<{ src: string; srcLang: string; label: string; default?: boolean }>;
};

/**
 * Normalize a video part into render-ready props.
 * Returns null if there is no usable url/src. Normalizes url -> src and
 * defaults downloadName from `name` when present.
 */
export function toVideoProps(
  input: VideoPartInput & {
    title?: string;
    poster?: string;
    downloadName?: string;
    captions?: NormalizedVideo['captions'];
  }
): NormalizedVideo | null {
  const src = input.url ?? input.src;
  if (!src) return null;
  return {
    src,
    title: input.title,
    poster: input.poster,
    mediaType: input.mediaType,
    downloadName: input.downloadName ?? input.name,
    captions: input.captions,
  };
}

function isDataVideoUrl(value: string): boolean {
  return value.toLowerCase().startsWith('data:video/');
}

function extractDataMediaType(value: string): string | undefined {
  const match = /^data:(video\/[a-z0-9.+-]+)/i.exec(value);
  return match?.[1];
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined;
}

/**
 * Extract a playable video from an arbitrary tool-result value (string OR
 * object). Used by ToolOutput. Conservative: never classifies arbitrary URLs
 * as video unless the extension/mediaType says so.
 */
export function extractVideoFromToolResult(output: unknown): NormalizedVideo | null {
  if (output == null) return null;

  if (typeof output === 'string') {
    const trimmed = output.trim();
    if (!trimmed) return null;

    if (isDataVideoUrl(trimmed)) {
      return { src: trimmed };
    }

    if (isVideoUrl(trimmed)) {
      return { src: trimmed };
    }

    // Try to parse a JSON string and recurse into the resulting value.
    const looksLikeJson =
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'));
    if (looksLikeJson) {
      try {
        const parsed = JSON.parse(trimmed);
        return extractVideoFromToolResult(parsed);
      } catch {
        return null;
      }
    }

    return null;
  }

  if (typeof output === 'object') {
    const obj = output as Record<string, unknown>;
    const urlKeys = ['url', 'src', 'video_url', 'videoUrl', 'download_url'] as const;

    const mediaType = asString(obj.mediaType) ?? asString(obj.mime_type);
    const type = asString(obj.type);
    const name = asString(obj.name) ?? asString(obj.filename);
    const title = asString(obj.title) ?? name;
    const poster = asString(obj.poster);
    const objectIndicatesVideo =
      isVideoMediaType(mediaType) || isVideoMediaType(type) || type === 'video';

    for (const key of urlKeys) {
      const value = asString(obj[key]);
      if (!value) continue;

      const dataVideo = isDataVideoUrl(value);
      if (isVideoUrl(value) || dataVideo || objectIndicatesVideo) {
        return {
          src: value,
          mediaType: mediaType ?? (dataVideo ? extractDataMediaType(value) : undefined),
          title,
          poster,
          downloadName: asString(obj.name) ?? asString(obj.filename) ?? asString(obj.title),
        };
      }
    }

    return null;
  }

  return null;
}
