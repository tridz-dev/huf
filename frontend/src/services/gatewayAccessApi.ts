import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export type GatewayAccessEntryState = 'Pending' | 'Approved' | 'Revoked' | 'Blocked' | 'Opted out';
export type GatewayAccessEntryType = 'Sender' | 'Room';

export interface GatewayAccessEntry {
  name: string;
  gateway: string;
  provider: string;
  entry_type: GatewayAccessEntryType;
  external_id: string;
  pairing_code?: string;
  state: GatewayAccessEntryState;
  expires_at?: string;
  display_label?: string;
  approved_by?: string;
  approved_at?: string;
  revoked_at?: string;
  revoked_by?: string;
  notes?: string;
  creation: string;
}

export interface ApproveGatewayPairingResult {
  name: string;
  state: 'Approved';
  gateway: string;
  provider: string;
  external_id: string;
  notification_status: string;
}

/** List Gateway Access Entries, defaulting to the pending-approval queue. */
export async function listGatewayAccessEntries(params?: {
  gateway?: string;
  state?: GatewayAccessEntryState;
}): Promise<GatewayAccessEntry[]> {
  try {
    const result = await call.get('huf.ai.gateway_service.list_gateway_access_entries', {
      gateway: params?.gateway,
      state: params?.state ?? 'Pending',
    });
    return (result.message as GatewayAccessEntry[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error listing pending access requests');
  }
}

/** Approve a pending Gateway Access Entry by its PAIR-XXXX code or entry name. */
export async function approveGatewayPairing(
  codeOrEntryName: string,
  notes?: string
): Promise<ApproveGatewayPairingResult> {
  try {
    const result = await call.post('huf.ai.gateway_service.approve_gateway_pairing', {
      code_or_entry_name: codeOrEntryName,
      notes,
    });
    return result.message as ApproveGatewayPairingResult;
  } catch (error) {
    handleFrappeError(error, `Error approving pairing request ${codeOrEntryName}`);
  }
}

/** Revoke a Gateway Access Entry, pending or previously approved. */
export async function revokeGatewayAccessEntry(entryName: string): Promise<{ name: string; state: 'Revoked' }> {
  try {
    const result = await call.post('huf.ai.gateway_service.revoke_gateway_access_entry', {
      entry_name: entryName,
    });
    return result.message as { name: string; state: 'Revoked' };
  } catch (error) {
    handleFrappeError(error, `Error revoking access entry ${entryName}`);
  }
}

/** Block a sender for good: ignored silently and never paired again until unblocked. */
export async function blockGatewayAccessEntry(entryName: string): Promise<{ name: string; state: GatewayAccessEntryState }> {
  try {
    const result = await call.post('huf.ai.gateway_service.block_gateway_access_entry', { entry_name: entryName });
    return result.message;
  } catch (error) {
    handleFrappeError(error, `Error blocking ${entryName}`);
  }
}

/** Lift a block; the sender can ask for access again. */
export async function unblockGatewayAccessEntry(entryName: string): Promise<{ name: string; state: GatewayAccessEntryState }> {
  try {
    const result = await call.post('huf.ai.gateway_service.unblock_gateway_access_entry', { entry_name: entryName });
    return result.message;
  } catch (error) {
    handleFrappeError(error, `Error unblocking ${entryName}`);
  }
}

/** Give a removed or declined sender access again (sends the welcome message). */
export async function restoreGatewayAccessEntry(
  entryName: string,
): Promise<{ name: string; state: 'Approved'; notification_status: string }> {
  try {
    const result = await call.post('huf.ai.gateway_service.restore_gateway_access_entry', { entry_name: entryName });
    return result.message;
  } catch (error) {
    handleFrappeError(error, `Error restoring ${entryName}`);
  }
}

/** Approve a phone number (or room) by hand, e.g. for the Allow list policy. */
export async function addGatewayAccessEntry(params: {
  gateway: string;
  externalId: string;
  displayLabel?: string;
  entryType?: GatewayAccessEntryType;
}): Promise<{ name: string; state: 'Approved'; external_id: string }> {
  try {
    const result = await call.post('huf.ai.gateway_service.add_gateway_access_entry', {
      gateway: params.gateway,
      external_id: params.externalId,
      display_label: params.displayLabel,
      entry_type: params.entryType ?? 'Sender',
    });
    return result.message;
  } catch (error) {
    handleFrappeError(error, 'Error adding the number');
  }
}
