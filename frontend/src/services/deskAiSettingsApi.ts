import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

/** The `DeskAI Settings` Single doctype, owned by the separate `deskai` Frappe app. */
export interface DeskAiSettingsDoc {
  enabled: 0 | 1;
  default_agent?: string;
}

/**
 * Fetch the `DeskAI Settings` singleton.
 *
 * The `deskai` app is optional — if it isn't installed on this site, the
 * doctype doesn't exist and the read throws (404 / "DocType not found").
 * Callers should treat a thrown error here as "DeskAI is not installed"
 * rather than a generic failure.
 */
export async function getDeskAiSettings(): Promise<DeskAiSettingsDoc> {
  return await db.getDoc(doctype['DeskAI Settings'], doctype['DeskAI Settings']);
}

/** Update the `DeskAI Settings` singleton. Throws if the `deskai` app isn't installed. */
export async function updateDeskAiSettings(data: Partial<DeskAiSettingsDoc>): Promise<void> {
  await db.updateDoc(doctype['DeskAI Settings'], doctype['DeskAI Settings'], data);
}
