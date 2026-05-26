import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Filters for Frappe get_count
 */
export type CountFilters = Array<[string, string, unknown]>;

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

/**
 * Fetch total count for paginated list responses.
 * Skips the count API call when the list is empty (returns 0) to avoid redundant requests.
 *
 * @param page - Current page (count only fetched for page 1)
 * @param itemCount - Number of items in the current page
 * @param targetDoctype - The DocType name to count
 * @param filters - Filters matching the list query
 * @returns Total count, 0 when empty, or undefined for non-first pages / on error
 */
export async function fetchPaginatedCount(
  page: number,
  itemCount: number,
  targetDoctype: string,
  filters?: CountFilters
): Promise<number | undefined> {
  if (page !== 1) return undefined;
  if (itemCount === 0) return 0;
  try {
    return await fetchDocCount(targetDoctype, filters);
  } catch {
    return undefined;
  }
}

