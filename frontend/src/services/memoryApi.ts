import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export const memoryApi = {
  getMemoryRecords: async (query?: string, scopeType?: string) => {
    try {
      const response = await call.post('huf.ai.memory_tools.search_memory_records', {
        query: query || null,
        scope_type: scopeType || null,
        status: 'Active',
        limit: 50
      });
      return response.message || response.results || [];
    } catch (error) {
      throw handleFrappeError(error, 'Failed to fetch memory records');
    }
  },

  archiveMemoryRecord: async (memoryRecordId: string) => {
    try {
      const response = await call.post('huf.ai.memory_tools.archive_memory_record', {
        memory_record: memoryRecordId
      });
      return response;
    } catch (error) {
      throw handleFrappeError(error, 'Failed to archive memory record');
    }
  }
};
