import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CopyField } from '@/components/ui/copy-field';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import {
  completeSignup,
  getSignupConfig,
  type CompleteSignupResult,
  type SignupConfig,
} from '@/services/channels/embeddedSignupApi';

const SDK_URL = 'https://connect.facebook.net/en_US/sdk.js';
const FB_ORIGIN = /^https:\/\/([a-z0-9-]+\.)*facebook\.com$/;

export interface EmbeddedSignupData {
  waba_id: string;
  phone_number_id: string;
  business_id?: string;
}

/** True only for https origins on facebook.com (and its subdomains). */
export function isFacebookOrigin(origin: string): boolean {
  return FB_ORIGIN.test(origin);
}

export type SignupMessage =
  | { kind: 'finish'; data: EmbeddedSignupData }
  | { kind: 'cancel' | 'error'; message?: string };

/** Parse a window `message` event from the Embedded Signup popup; null for anything else. */
export function parseSignupMessage(ev: { origin: string; data: unknown }): SignupMessage | null {
  if (!isFacebookOrigin(ev.origin)) return null;
  let payload: unknown = ev.data;
  if (typeof payload === 'string') {
    try {
      payload = JSON.parse(payload);
    } catch {
      return null;
    }
  }
  if (!payload || typeof payload !== 'object') return null;
  const p = payload as { type?: unknown; event?: unknown; data?: unknown };
  if (p.type !== 'WA_EMBEDDED_SIGNUP') return null;
  const d = (p.data && typeof p.data === 'object' ? p.data : {}) as Record<string, unknown>;
  if (typeof p.event === 'string' && p.event.startsWith('FINISH')) {
    const waba = String(d.waba_id ?? '');
    const phone = String(d.phone_number_id ?? '');
    if (!waba || !phone) return { kind: 'error', message: 'Meta did not return a phone number.' };
    return {
      kind: 'finish',
      data: { waba_id: waba, phone_number_id: phone, business_id: d.business_id ? String(d.business_id) : undefined },
    };
  }
  if (p.event === 'CANCEL') return { kind: 'cancel' };
  if (p.event === 'ERROR') return { kind: 'error', message: typeof d.error_message === 'string' ? d.error_message : undefined };
  return null;
}

interface FbSdk {
  init: (o: Record<string, unknown>) => void;
  login: (cb: (r: { authResponse?: { code?: string } | null }) => void, o: Record<string, unknown>) => void;
}
type FbWindow = Window & { FB?: FbSdk; fbAsyncInit?: () => void };

let sdkPromise: Promise<FbSdk> | null = null;

/** Load the Facebook JS SDK on demand (never at page load). */
export function loadFbSdk(config: SignupConfig): Promise<FbSdk> {
  const w = window as FbWindow;
  if (w.FB) return Promise.resolve(w.FB);
  sdkPromise ??= new Promise<FbSdk>((resolve, reject) => {
    w.fbAsyncInit = () => {
      w.FB!.init({ appId: config.app_id, autoLogAppEvents: true, xfbml: false, version: config.graph_version });
      resolve(w.FB!);
    };
    const s = document.createElement('script');
    s.src = SDK_URL;
    s.async = true;
    s.crossOrigin = 'anonymous';
    s.onerror = () => {
      sdkPromise = null;
      reject(new Error('Could not load Facebook. Check your connection or ad blocker.'));
    };
    document.body.appendChild(s);
  });
  return sdkPromise;
}

export interface EmbeddedSignupStepProps {
  gatewayName?: string;
  onConnected: (result: CompleteSignupResult) => void;
}

export function EmbeddedSignupStep({ gatewayName, onConnected }: EmbeddedSignupStepProps) {
  const [config, setConfig] = useState<SignupConfig | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pinResult, setPinResult] = useState<CompleteSignupResult | null>(null);
  const code = useRef<string | null>(null);
  const info = useRef<EmbeddedSignupData | null>(null);
  const listener = useRef<((ev: MessageEvent) => void) | null>(null);

  useEffect(() => {
    let live = true;
    getSignupConfig()
      .then((c) => live && setConfig(c))
      .catch(() => live && setConfig(null))
      .finally(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, []);

  const stopListening = useCallback(() => {
    if (listener.current) window.removeEventListener('message', listener.current);
    listener.current = null;
  }, []);
  useEffect(() => stopListening, [stopListening]);

  const finish = useCallback(async () => {
    if (!code.current || !info.current) return;
    const args = { code: code.current, ...info.current, gateway_name: gatewayName };
    code.current = null;
    stopListening();
    try {
      const res = await completeSignup(args);
      if (res.pin) setPinResult(res);
      else onConnected(res);
    } catch (e) {
      setError(getFrappeErrorMessage(e) || 'Could not finish the signup.');
    } finally {
      setBusy(false);
    }
  }, [gatewayName, onConnected, stopListening]);

  const start = async () => {
    if (!config?.enabled) return;
    setError('');
    setBusy(true);
    code.current = null;
    info.current = null;
    stopListening();
    const onMessage = (ev: MessageEvent) => {
      const msg = parseSignupMessage(ev);
      if (!msg) return;
      if (msg.kind === 'finish') {
        info.current = msg.data;
        void finish();
      } else {
        stopListening();
        setBusy(false);
        if (msg.kind === 'error') setError(msg.message || 'Meta reported an error during signup.');
      }
    };
    listener.current = onMessage;
    window.addEventListener('message', onMessage);
    try {
      const fb = await loadFbSdk(config);
      fb.login(
        (r) => {
          const c = r.authResponse?.code;
          if (!c) {
            stopListening();
            setBusy(false);
            return;
          }
          code.current = c;
          void finish();
        },
        {
          config_id: config.config_id,
          response_type: 'code',
          override_default_response_type: true,
          extras: { setup: {}, featureType: '', sessionInfoVersion: '3' },
        },
      );
    } catch (e) {
      stopListening();
      setBusy(false);
      setError(e instanceof Error ? e.message : 'Could not start Facebook signup.');
    }
  };

  if (pinResult) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-ink">Connected. Save this two-step verification PIN; it is shown only once.</p>
        <CopyField label="PIN" value={pinResult.pin ?? ''} />
        <Button onClick={() => onConnected(pinResult)}>Continue</Button>
      </div>
    );
  }

  const enabled = !!config?.enabled;
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-ink">Connect with Facebook</p>
          <p className="text-sm text-steel">Recommended. Log in to Meta and pick your number, no copy and paste.</p>
        </div>
        <Button variant="outline" disabled={!enabled || busy} onClick={() => void start()} aria-describedby="fb-state">
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}
          Connect with Facebook
        </Button>
      </div>
      {loaded && !enabled && (
        <p id="fb-state" className="mt-2 text-xs text-steel">
          Not configured. An admin can set this up under Settings, Facebook signup.
        </p>
      )}
      {error && (
        <p id="fb-error" role="alert" className="mt-2 text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
