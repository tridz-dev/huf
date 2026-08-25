import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface ErpnextDemoSetupResult {
  created: string[];
  already_present: string[];
  skipped_reason: string | null;
}

/**
 * Create the minimum ERPNext master data (Warehouse Type, Item Group /
 * Customer Group leaves, Territory, Price List, Fiscal Year) needed to
 * exercise a demo Procedure against a fresh ERPNext install. Idempotent —
 * safe to call more than once. Backed by the whitelisted, System-Manager-
 * only method `huf.ai.erpnext_demo_setup.run_ensure_erpnext_demo_masters`.
 */
export async function runErpnextDemoSetup(): Promise<ErpnextDemoSetupResult | undefined> {
  try {
    const result = await call.post('huf.ai.erpnext_demo_setup.run_ensure_erpnext_demo_masters');
    return result?.message as ErpnextDemoSetupResult | undefined;
  } catch (error) {
    handleFrappeError(error, 'Error setting up ERPNext demo data');
  }
}
