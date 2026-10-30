import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const METHOD = 'huf.ai.secrets.stash_secret';

export interface StashSecretResult {
  credentials_ref: string;
  fields: string[];
}

export type StashSecretOutcome =
  | ({ ok: true } & StashSecretResult)
  | { ok: false; message: string };

/**
 * Store a secret card's values in the short-lived server-side stash.
 * Returns only the opaque credentials reference and the field ids; the values
 * are never echoed back. Errors are returned, not thrown, and never include values.
 */
export async function stashSecret(
  values: Record<string, string>,
  purpose: string,
  gateway?: string,
): Promise<StashSecretOutcome> {
  const args: Record<string, unknown> = { values, purpose };
  if (gateway) args.gateway = gateway;
  try {
    const res = await call.post(METHOD, args);
    const data = (res as { message?: Partial<StashSecretResult> } | null)?.message ?? (res as Partial<StashSecretResult> | null);
    if (!data || typeof data.credentials_ref !== 'string' || !data.credentials_ref) {
      return { ok: false, message: 'The credentials could not be stored. Try again.' };
    }
    return {
      ok: true,
      credentials_ref: data.credentials_ref,
      fields: Array.isArray(data.fields) ? data.fields.map(String) : Object.keys(values),
    };
  } catch (err) {
    return { ok: false, message: getFrappeErrorMessage(err) };
  }
}
