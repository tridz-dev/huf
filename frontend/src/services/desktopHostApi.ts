/**
 * Desktop-hosted conversations (Desktop Remote Sessions).
 *
 * A conversation created by Huf Desktop is pinned to that computer (`execution_host = desktop`).
 * The web client of the same user can continue it remotely. This module wraps the whitelisted
 * endpoints in `huf.ai.desktop_sessions` and turns the structured (non-raising) run failures
 * `desktop_offline`, `workspace_changed`, `remote_disabled` and `permission_denied` into a typed
 * error the composer can render.
 */
import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export type PermissionMode = 'auto' | 'sandbox' | 'ask' | 'full';

export const PERMISSION_MODES: readonly PermissionMode[] = ['auto', 'sandbox', 'ask', 'full'] as const;

export const PERMISSION_MODE_LABELS: Record<PermissionMode, string> = {
  auto: 'Auto',
  sandbox: 'Sandbox',
  ask: 'Ask',
  full: 'Full',
};

export function isPermissionMode(value: unknown): value is PermissionMode {
  return typeof value === 'string' && (PERMISSION_MODES as readonly string[]).includes(value);
}

/** One row of `list_desktop_hosts`. `last_seen` is epoch milliseconds. */
export interface DesktopHost {
  device_id: string;
  label: string | null;
  online: boolean;
  last_seen: number | null;
  remote_control: boolean;
  mode: string | null;
}

export type DesktopRunErrorCode =
  | 'desktop_offline'
  | 'workspace_changed'
  | 'remote_disabled'
  | 'permission_denied';

const DESKTOP_RUN_ERROR_CODES: readonly string[] = [
  'desktop_offline',
  'workspace_changed',
  'remote_disabled',
  'permission_denied',
];

/** Which switch blocks a remote run: the desktop's remote-control switch or the agent's flag. */
export type RemoteDisabledBy = 'desktop' | 'agent';

/** A run against a desktop-hosted conversation that the server declined without creating anything. */
export class DesktopRunError extends Error {
  readonly code: DesktopRunErrorCode;
  readonly lastSeen: number | null;
  readonly disabledBy: RemoteDisabledBy | null;
  readonly hostDeviceId: string | null;
  readonly hostLabel: string | null;

  constructor(
    code: DesktopRunErrorCode,
    message: string,
    extra: {
      lastSeen?: number | null;
      disabledBy?: RemoteDisabledBy | null;
      hostDeviceId?: string | null;
      hostLabel?: string | null;
    } = {},
  ) {
    super(message);
    this.name = 'DesktopRunError';
    this.code = code;
    this.lastSeen = extra.lastSeen ?? null;
    this.disabledBy = extra.disabledBy ?? null;
    this.hostDeviceId = extra.hostDeviceId ?? null;
    this.hostLabel = extra.hostLabel ?? null;
  }
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null;
}

/**
 * Recognise a structured desktop failure in a run-start response body (`response.message`, or the
 * nested `run` object `new_conversation` uses). Returns `null` for every other response, including
 * ordinary failures, so the existing error path is untouched.
 */
export function parseDesktopRunFailure(body: unknown): DesktopRunError | null {
  if (!body || typeof body !== 'object') return null;
  const b = body as Record<string, unknown>;
  if (b.success !== false) return null;
  const code = typeof b.code === 'string' ? b.code : typeof b.error === 'string' ? b.error : null;
  if (!code || !DESKTOP_RUN_ERROR_CODES.includes(code)) return null;
  const disabledBy = b.disabled_by === 'desktop' || b.disabled_by === 'agent' ? b.disabled_by : null;
  return new DesktopRunError(
    code as DesktopRunErrorCode,
    asString(b.message) ?? 'The desktop could not run this conversation.',
    {
      lastSeen: asNumber(b.last_seen),
      disabledBy,
      hostDeviceId: asString(b.host_device_id),
      hostLabel: asString(b.host_label),
    },
  );
}

/** The plain-language reason a mode change failed, from the server's structured error. */
export function permissionModeErrorText(error: {
  code: string;
  message: string;
  appliedMode?: string | null;
  lastSeen?: number | null;
}): string {
  switch (error.code) {
    case 'mode_not_applied': {
      const still = isPermissionMode(error.appliedMode) ? PERMISSION_MODE_LABELS[error.appliedMode] : null;
      return still
        ? `The desktop did not apply that mode. It is still on ${still}.`
        : 'The desktop did not apply that mode.';
    }
    case 'remote_disabled':
      return 'Remote control is off on this desktop. Turn it on in Huf Desktop to change the mode from here.';
    case 'desktop_offline':
      return `The desktop is offline (last seen ${formatLastSeen(error.lastSeen)}).`;
    default:
      return error.message;
  }
}

/** Relative "last seen" text for an epoch-millisecond timestamp. */
export function formatLastSeen(lastSeenMs: number | null | undefined, now: number = Date.now()): string {
  if (lastSeenMs == null || !Number.isFinite(lastSeenMs)) return 'not seen recently';
  const seconds = Math.max(0, Math.floor((now - lastSeenMs) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return `${days} d ago`;
}

function unwrap<T>(result: unknown): T {
  const r = result as { message?: unknown } | null | undefined;
  return (r && typeof r === 'object' && 'message' in r ? r.message : result) as T;
}

/** The session user's desktop devices (online state, last seen, remote-control switch, mode). */
export async function listDesktopHosts(): Promise<DesktopHost[]> {
  try {
    const result = await call.get('huf.ai.desktop_sessions.list_desktop_hosts');
    const rows = unwrap<unknown>(result);
    return Array.isArray(rows) ? (rows as DesktopHost[]) : [];
  } catch (error) {
    handleFrappeError(error, 'Error loading desktop devices');
  }
}

export interface SetPermissionModeResult {
  ok: boolean;
  appliedMode?: string;
  error?: { code: string; message: string; appliedMode?: string | null; lastSeen?: number | null };
}

/**
 * Ask the desktop to switch a workspace's permission mode. The server answers with the mode the
 * desktop confirmed (`ok: true`) or a structured error (`mode_not_applied`, `remote_disabled`,
 * `desktop_offline`, ...); those are returned, not thrown.
 */
export async function setDesktopPermissionMode(
  deviceId: string,
  mode: PermissionMode,
): Promise<SetPermissionModeResult> {
  try {
    const result = await call.post('huf.ai.desktop_sessions.set_desktop_permission_mode', {
      device_id: deviceId,
      mode,
    });
    const body = unwrap<Record<string, unknown> | undefined>(result) ?? {};
    if (body.ok === true) {
      return { ok: true, appliedMode: asString(body.applied_mode) ?? undefined };
    }
    const err = (body.error ?? {}) as Record<string, unknown>;
    return {
      ok: false,
      error: {
        code: asString(err.code) ?? 'internal',
        message: asString(err.message) ?? 'The desktop did not apply the change.',
        appliedMode: asString(err.applied_mode),
        lastSeen: asNumber(err.last_seen),
      },
    };
  } catch (error) {
    handleFrappeError(error, 'Error changing the permission mode');
  }
}

export interface RebindResult {
  ok: boolean;
  hostLabel?: string;
  error?: { code: string; message: string; lastSeen?: number | null };
}

/** Move a desktop-hosted conversation to the workspace its device has open now. */
export async function rebindDesktopConversation(
  conversation: string,
  workspaceFingerprint?: string,
): Promise<RebindResult> {
  try {
    const result = await call.post('huf.ai.desktop_sessions.rebind_desktop_conversation', {
      conversation,
      workspace_fingerprint: workspaceFingerprint,
    });
    const body = unwrap<Record<string, unknown> | undefined>(result) ?? {};
    if (body.ok === true) {
      return { ok: true, hostLabel: asString(body.host_label) ?? undefined };
    }
    const err = (body.error ?? {}) as Record<string, unknown>;
    return {
      ok: false,
      error: {
        code: asString(err.code) ?? 'internal',
        message: asString(err.message) ?? 'The conversation could not be rebound.',
        lastSeen: asNumber(err.last_seen),
      },
    };
  } catch (error) {
    handleFrappeError(error, 'Error rebinding the conversation');
  }
}
