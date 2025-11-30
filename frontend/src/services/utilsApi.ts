import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Fetch count for a given DocType using frappe.client.get_count
 * 
 * @param targetDoctype - The DocType name to count
 * @param filters - Optional array of filters in format [field, operator, value]
 * @returns The count of documents, or undefined if an error occurs
 */
export async function fetchDocCount(
  targetDoctype: string,
  filters?: Array<[string, string, unknown]>
): Promise<number | undefined> {
  const params: Record<string, unknown> = { doctype: targetDoctype };
  if (filters && filters.length > 0) {
    params.filters = JSON.stringify(filters);
  }

  try {
    const response = await call.get('frappe.client.get_count', params);
    const { message } = response || {};

    if (typeof message === 'number') {
      return message;
    }

    if (typeof message === 'string') {
      const parsed = Number(message);
      return Number.isNaN(parsed) ? undefined : parsed;
    }

    return undefined;
  } catch (error) {
    handleFrappeError(error, `Error fetching count for ${targetDoctype}`);
    return undefined;
  }
}

