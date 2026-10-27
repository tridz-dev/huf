import { errorInfo } from '@/components/whatsapp/messageLogModel';

const TOKEN_REJECTED = 'Meta rejected the access token. Replace it in settings.';

/** True when a stored gateway error means Meta no longer accepts the access token. */
export function isTokenRejected(raw?: string | null): boolean {
  const text = raw ?? '';
  return errorInfo(text)?.code === 190 || /\boauth\b|invalid.*token|token.*(expired|invalid)|access token/i.test(text);
}

/** Plain wording for a stored gateway error; never the raw Meta or server text. */
export function gatewayErrorText(raw?: string | null): string {
  if (!raw?.trim()) return '';
  if (isTokenRejected(raw)) return TOKEN_REJECTED;
  const info = errorInfo(raw);
  if (info && info.code !== null && !info.label.startsWith('Error ')) return info.hint;
  return 'The last message ran into an error.';
}
