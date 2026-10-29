import { useParams } from 'react-router-dom';

const KEY = 'huf.channels.whatsapp.lastGateway';

export function getLastGateway(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function rememberGateway(name: string) {
  try {
    localStorage.setItem(KEY, name);
  } catch {
    void 0;
  }
}

/** Gateway name from the `n/:gw/...` path; undefined on gateway-less routes. */
export function useChannelGateway(): string | undefined {
  const { gw } = useParams<{ gw?: string }>();
  return gw ? decodeURIComponent(gw) : undefined;
}
