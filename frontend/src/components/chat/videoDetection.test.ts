import { describe, it, expect } from 'vitest';
import {
  VIDEO_EXTENSIONS,
  isVideoMediaType,
  isVideoUrl,
  isAllowedVideoSrc,
  detectVideo,
  toVideoProps,
  extractVideoFromToolResult,
} from './videoDetection';

describe('VIDEO_EXTENSIONS', () => {
  it('exposes the supported extensions', () => {
    expect(VIDEO_EXTENSIONS).toEqual(['.mp4', '.webm', '.ogv', '.mov', '.m4v']);
  });
});

describe('isAllowedVideoSrc', () => {
  it('allows http/https', () => {
    expect(isAllowedVideoSrc('http://example.com/a.mp4')).toBe(true);
    expect(isAllowedVideoSrc('https://example.com/a.mp4')).toBe(true);
  });

  it('allows data: and blob: URIs', () => {
    expect(isAllowedVideoSrc('data:video/mp4;base64,AAAA')).toBe(true);
    expect(isAllowedVideoSrc('blob:https://example.com/uuid')).toBe(true);
  });

  it('allows relative URLs (resolve against page origin)', () => {
    expect(isAllowedVideoSrc('/files/clip.mp4')).toBe(true);
    expect(isAllowedVideoSrc('files/clip.mp4')).toBe(true);
  });

  it('rejects dangerous schemes', () => {
    expect(isAllowedVideoSrc('javascript:alert(1)')).toBe(false);
    expect(isAllowedVideoSrc('vbscript:msgbox(1)')).toBe(false);
    expect(isAllowedVideoSrc('file:///etc/passwd')).toBe(false);
  });

  it('rejects empty/invalid input', () => {
    expect(isAllowedVideoSrc('')).toBe(false);
  });
});

describe('isVideoMediaType', () => {
  it('returns true for video/* media types', () => {
    expect(isVideoMediaType('video/mp4')).toBe(true);
    expect(isVideoMediaType('video/webm')).toBe(true);
    expect(isVideoMediaType('video/ogg; codecs=theora')).toBe(true);
  });

  it('returns false for non-video media types', () => {
    expect(isVideoMediaType('image/png')).toBe(false);
    expect(isVideoMediaType('audio/mpeg')).toBe(false);
    expect(isVideoMediaType('application/json')).toBe(false);
  });

  it('returns false for empty, null, or undefined', () => {
    expect(isVideoMediaType('')).toBe(false);
    expect(isVideoMediaType(null)).toBe(false);
    expect(isVideoMediaType(undefined)).toBe(false);
  });
});

describe('isVideoUrl', () => {
  it('returns true for supported video extensions', () => {
    expect(isVideoUrl('https://cdn.example.com/clip.mp4')).toBe(true);
    expect(isVideoUrl('https://cdn.example.com/clip.webm')).toBe(true);
    expect(isVideoUrl('https://cdn.example.com/clip.mov')).toBe(true);
    expect(isVideoUrl('/files/clip.MP4')).toBe(true);
  });

  it('strips query strings and hashes before testing the extension', () => {
    expect(isVideoUrl('https://cdn.example.com/clip.mp4?token=abc')).toBe(true);
    expect(isVideoUrl('https://cdn.example.com/clip.webm#t=10')).toBe(true);
    expect(isVideoUrl('https://cdn.example.com/clip.mp4?download=1#frag')).toBe(true);
  });

  it('returns false for non-video extensions', () => {
    expect(isVideoUrl('https://cdn.example.com/image.png')).toBe(false);
    expect(isVideoUrl('https://cdn.example.com/doc.pdf')).toBe(false);
    expect(isVideoUrl('https://cdn.example.com/clip.mp4x')).toBe(false);
  });

  it('does not match just because the URL contains the words video or media', () => {
    expect(isVideoUrl('https://example.com/video/watch')).toBe(false);
    expect(isVideoUrl('https://example.com/media/page')).toBe(false);
    expect(isVideoUrl('https://example.com/video.mp4.html')).toBe(false);
  });

  it('returns false for empty, null, or undefined', () => {
    expect(isVideoUrl('')).toBe(false);
    expect(isVideoUrl(null)).toBe(false);
    expect(isVideoUrl(undefined)).toBe(false);
  });
});

describe('detectVideo priority', () => {
  it("prefers type === 'video' above all else", () => {
    expect(detectVideo({ type: 'video', mediaType: 'image/png' })).toBe(true);
  });

  it('falls back to mediaType when type is absent', () => {
    expect(detectVideo({ mediaType: 'video/mp4' })).toBe(true);
    expect(detectVideo({ mediaType: 'image/png' })).toBe(false);
  });

  it('falls back to category after mediaType', () => {
    expect(detectVideo({ category: 'video' })).toBe(true);
    expect(detectVideo({ category: 'image' })).toBe(false);
  });

  it('falls back to url / src / name last', () => {
    expect(detectVideo({ url: 'https://x.com/a.mp4' })).toBe(true);
    expect(detectVideo({ src: 'https://x.com/a.webm' })).toBe(true);
    expect(detectVideo({ name: 'https://x.com/a.mov' })).toBe(true);
    expect(detectVideo({ url: 'https://x.com/a.png' })).toBe(false);
  });

  it('respects the priority order end-to-end', () => {
    // type wins even though url is non-video
    expect(detectVideo({ type: 'video', url: 'https://x.com/a.png' })).toBe(true);
    // mediaType wins even though category is non-video and url is non-video
    expect(
      detectVideo({ mediaType: 'video/mp4', category: 'image', url: 'https://x.com/a.png' })
    ).toBe(true);
    // category wins over url
    expect(detectVideo({ category: 'video', url: 'https://x.com/a.png' })).toBe(true);
  });
});

describe('toVideoProps', () => {
  it('normalizes url to src and defaults downloadName to name', () => {
    expect(toVideoProps({ url: 'https://x.com/a.mp4', name: 'a.mp4' })).toEqual({
      src: 'https://x.com/a.mp4',
      title: undefined,
      poster: undefined,
      mediaType: undefined,
      downloadName: 'a.mp4',
      captions: undefined,
    });
  });

  it('uses src when url is absent', () => {
    const result = toVideoProps({ src: 'https://x.com/a.webm' });
    expect(result).not.toBeNull();
    expect(result?.src).toBe('https://x.com/a.webm');
  });

  it('prefers an explicit downloadName over name', () => {
    const result = toVideoProps({ url: 'https://x.com/a.mp4', name: 'a.mp4', downloadName: 'b.mp4' });
    expect(result?.downloadName).toBe('b.mp4');
  });

  it('returns null when neither url nor src is present', () => {
    expect(toVideoProps({ name: 'a.mp4' })).toBeNull();
    expect(toVideoProps({})).toBeNull();
  });

  it('preserves optional metadata fields', () => {
    const captions = [{ src: 'a.vtt', srcLang: 'en', label: 'English', default: true }];
    const result = toVideoProps({
      url: 'https://x.com/a.mp4',
      title: 'Title',
      poster: 'poster.jpg',
      mediaType: 'video/mp4',
      captions,
    });
    expect(result?.title).toBe('Title');
    expect(result?.poster).toBe('poster.jpg');
    expect(result?.mediaType).toBe('video/mp4');
    expect(result?.captions).toEqual(captions);
  });
});

describe('extractVideoFromToolResult', () => {
  it('returns { src } for a bare video URL string', () => {
    expect(extractVideoFromToolResult('https://x.com/a.mp4')).toEqual({ src: 'https://x.com/a.mp4' });
  });

  it('returns { src } for a data:video/ URI', () => {
    const data = 'data:video/mp4;base64,AAAA';
    expect(extractVideoFromToolResult(data)).toEqual({ src: data });
  });

  it('returns null for a non-video string', () => {
    expect(extractVideoFromToolResult('not-a-video')).toBeNull();
    expect(extractVideoFromToolResult('https://x.com/a.png')).toBeNull();
  });

  it('parses JSON strings and recurses', () => {
    const json = JSON.stringify({ url: 'https://x.com/a.mp4' });
    expect(extractVideoFromToolResult(json)).toEqual({
      src: 'https://x.com/a.mp4',
      mediaType: undefined,
      title: undefined,
      downloadName: undefined,
      poster: undefined,
    });
  });

  it('returns null for malformed JSON strings', () => {
    expect(extractVideoFromToolResult('{not json')).toBeNull();
  });

  it('checks candidate keys in order and honors video extension', () => {
    expect(
      extractVideoFromToolResult({ url: 'https://x.com/a.mp4', src: 'https://x.com/b.webm' })
    ).toMatchObject({ src: 'https://x.com/a.mp4' });
    expect(
      extractVideoFromToolResult({ src: 'https://x.com/b.webm', video_url: 'https://x.com/c.mov' })
    ).toMatchObject({ src: 'https://x.com/b.webm' });
    expect(
      extractVideoFromToolResult({ video_url: 'https://x.com/c.mov', videoUrl: 'https://x.com/d.mp4' })
    ).toMatchObject({ src: 'https://x.com/c.mov' });
    expect(extractVideoFromToolResult({ videoUrl: 'https://x.com/d.mp4' })).toMatchObject({
      src: 'https://x.com/d.mp4',
    });
    expect(extractVideoFromToolResult({ download_url: 'https://x.com/e.m4v' })).toMatchObject({
      src: 'https://x.com/e.m4v',
    });
  });

  it('accepts a non-video extension when mediaType is video/*', () => {
    expect(
      extractVideoFromToolResult({ url: 'https://x.com/stream', mediaType: 'video/mp4' })
    ).toMatchObject({ src: 'https://x.com/stream', mediaType: 'video/mp4' });
    expect(
      extractVideoFromToolResult({ url: 'https://x.com/stream', mime_type: 'video/webm' })
    ).toMatchObject({ src: 'https://x.com/stream' });
    expect(extractVideoFromToolResult({ url: 'https://x.com/stream', type: 'video/mov' })).toMatchObject(
      { src: 'https://x.com/stream' }
    );
  });

  it('rejects a non-video url without a video mediaType', () => {
    expect(extractVideoFromToolResult({ url: 'https://x.com/a.png' })).toBeNull();
    expect(extractVideoFromToolResult({ url: 'https://x.com/a.png', mediaType: 'image/png' })).toBeNull();
  });

  it('carries name / filename / title into downloadName and title', () => {
    expect(extractVideoFromToolResult({ url: 'https://x.com/a.mp4', name: 'clip.mp4' })).toMatchObject({
      downloadName: 'clip.mp4',
      title: 'clip.mp4',
    });
    expect(
      extractVideoFromToolResult({ url: 'https://x.com/a.mp4', filename: 'file.mp4' })
    ).toMatchObject({ downloadName: 'file.mp4' });
    expect(extractVideoFromToolResult({ url: 'https://x.com/a.mp4', title: 'Nice' })).toMatchObject({
      downloadName: 'Nice',
    });
  });

  it('carries poster through', () => {
    expect(
      extractVideoFromToolResult({ url: 'https://x.com/a.mp4', poster: 'poster.jpg' })
    ).toMatchObject({ poster: 'poster.jpg' });
  });

  it('returns null for non-string, non-object inputs', () => {
    expect(extractVideoFromToolResult(null)).toBeNull();
    expect(extractVideoFromToolResult(undefined)).toBeNull();
    expect(extractVideoFromToolResult(123)).toBeNull();
    expect(extractVideoFromToolResult(['https://x.com/a.mp4'])).toBeNull();
  });
});
