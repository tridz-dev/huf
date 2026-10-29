import { useParams } from 'react-router-dom';
import { isChannelKey, type ChannelKey } from './channelsMeta';

const key = (channel: string) => `huf:channels:${channel}:lastGateway`;

export function getLastGateway(channel: string = 'whatsapp'): string | null {
  try {
    return localStorage.getItem(key(channel));
  } catch {
    return null;
  }
}

export function rememberGateway(name: string, channel: string = 'whatsapp') {
  try {
    localStorage.setItem(key(channel), name);
  } catch {
    void 0;
  }
}

/** Channel from the `/channels/:channel` path segment; WhatsApp when absent or unknown. */
export function useChannel(): ChannelKey {
  const { channel } = useParams<{ channel?: string }>();
  return isChannelKey(channel) ? channel : 'whatsapp';
}

/** Gateway name from the `n/:gw/...` path; undefined on gateway-less routes. */
export function useChannelGateway(): string | undefined {
  const { gw } = useParams<{ gw?: string }>();
  return gw ? decodeURIComponent(gw) : undefined;
}
