import { call } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export type CommerceResult<T> = { ok: true; data: T } | { ok: false; error: string };

export interface SyncResult {
  success: boolean;
  error?: string;
  items?: number;
  skipped?: number;
  batches?: number;
  synced?: number;
  failed?: number;
  errors?: string[];
}
export interface OrderRow {
  name: string;
  contact_handle?: string;
  total?: number;
  currency?: string;
  status?: string;
  payment_status?: string;
  creation?: string;
  conversation?: string;
  payment_link?: string;
}
export interface OrderItem { retailer_id?: string; item_name?: string; qty?: number; price?: number; currency?: string }
export interface OrderDetail extends OrderRow { items?: OrderItem[]; customer_note?: string }
export interface PackResult { success: boolean; error?: string; results?: Record<string, { success?: boolean; error?: string; message?: string }> }
export interface FlowRow { name: string; flow_id: string; flow_name?: string; status?: string; categories?: string; last_synced?: string }
export interface FlowResponseRow { name: string; flow?: string; conversation?: string; received_at?: string; flow_token?: string }

const unwrap = (res: unknown) => (res && typeof res === 'object' && 'message' in res ? (res as { message: unknown }).message : res);

async function run<T>(verb: 'get' | 'post', path: string, args: Record<string, unknown>): Promise<CommerceResult<T>> {
  try {
    const res = verb === 'post' ? await call.post(path, args) : await call.get(path, args);
    const body = (unwrap(res) ?? {}) as T & { success?: boolean; error?: string };
    return { ok: true, data: body };
  } catch (e) {
    return { ok: false, error: getFrappeErrorMessage(e) };
  }
}

const getList = <T>(doctype: string, fields: string[], filters: unknown, order_by: string, limit = 50) =>
  run<T[]>('get', 'frappe.client.get_list', { doctype, fields: JSON.stringify(fields), filters: JSON.stringify(filters), order_by, limit_page_length: limit });

const ORDER_FIELDS = ['name', 'contact_handle', 'total', 'currency', 'status', 'payment_status', 'creation', 'conversation', 'payment_link'];

export const syncCatalogNow = (gateway: string) => run<SyncResult>('post', 'huf.ai.channels.commerce.catalog.sync_catalog_now', { gateway });
export const listOrders = (gateway: string) => getList<OrderRow>('WhatsApp Order', ORDER_FIELDS, { gateway }, 'creation desc');
export const listConversationOrders = (conversation: string) =>
  getList<OrderRow>('WhatsApp Order', ORDER_FIELDS, { conversation }, 'creation desc', 3);
export const getOrder = (name: string) =>
  run<OrderDetail>('get', 'frappe.client.get', { doctype: 'WhatsApp Order', name });
export const createPaymentLink = (order: string) =>
  run<{ success: boolean; url?: string; error?: string }>('post', 'huf.ai.channels.commerce.payments.create_order_payment_link', { order });
export const submitTemplatesPack = (gateway: string) => run<PackResult>('post', 'huf.ai.channels.commerce.templates_pack.submit_templates_pack', { gateway });
export const listWaFlows = (gateway: string, refresh = 1) => run<FlowRow[]>('get', 'huf.ai.channels.wa_flows.list_wa_flows', { gateway, refresh });
export const listFlowResponses = (gateway: string) =>
  getList<FlowResponseRow>('WhatsApp Flow Response', ['name', 'flow', 'conversation', 'received_at', 'flow_token'], { gateway }, 'received_at desc', 20);
