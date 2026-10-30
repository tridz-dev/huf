import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { DataCatalog } from '@/lib/flow-data/types';

/** The steps before `nodeId` and the data each offers, with examples (people who can edit the flow only). */
export async function getDataCatalog(flowId: string, nodeId: string): Promise<DataCatalog> {
  try {
    const result = await call.post('huf.ai.flow.catalog.api.get_data_catalog', { flow_id: flowId, node_id: nodeId });
    return result.message as DataCatalog;
  } catch (error) {
    handleFrappeError(error, 'Error loading the data you can use');
  }
}
