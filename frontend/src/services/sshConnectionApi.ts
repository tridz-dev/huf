import { call, db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';
import { fetchPaginatedCount } from './utilsApi';

export interface SSHConnectionDoc {
  name: string;
  display_name: string;
  enabled?: 0 | 1;
  host: string;
  port?: number;
  username: string;
  auth_method: 'Password' | 'Private Key';
  password?: string;
  private_key?: string;
  private_key_passphrase?: string;
  host_key_verification?: string;
  host_key_fingerprint?: string;
  host_key_type?: string;
  host_key_enrolled_by?: string;
  host_key_enrolled_on?: string;
  last_tested_on?: string;
  last_test_status?: string;
  key_rotated_on?: string;
  last_error?: string;
  modified?: string;
}

export interface GetSSHConnectionsParams {
  page?: number;
  limit?: number;
  start?: number;
  search?: string;
  status?: 'enabled' | 'disabled' | 'all';
  [key: string]: unknown;
}

export interface PaginatedSSHConnectionsResponse {
  items: SSHConnectionDoc[];
  hasMore: boolean;
  total?: number;
}

export interface SSHTestResult {
  success: boolean;
  error?: string;
  fingerprint?: string;
  host_key_type?: string;
  host_key_enrolled?: boolean;
}

export async function getSSHConnections(
  params?: GetSSHConnectionsParams
): Promise<PaginatedSSHConnectionsResponse | SSHConnectionDoc[]> {
  try {
    if (!params) {
      const response = await db.getDocList(doctype['SSH Connection'], {
        fields: [
          'name',
          'display_name',
          'enabled',
          'host',
          'port',
          'username',
          'auth_method',
          'host_key_verification',
          'host_key_fingerprint',
          'host_key_type',
          'last_tested_on',
          'last_test_status',
          'last_error',
          'modified',
        ],
        limit: 100,
        orderBy: { field: 'modified', order: 'desc' },
      });

      return response as SSHConnectionDoc[];
    }

    const { page = 1, limit = 20, start = (page - 1) * limit, search, status = 'all' } = params;
    const filters: Array<[string, string, string | number | boolean]> = [];

    if (status === 'enabled') {
      filters.push(['enabled', '=', 1]);
    } else if (status === 'disabled') {
      filters.push(['enabled', '=', 0]);
    }

    if (search && search.trim()) {
      filters.push(['display_name', 'like', `%${search.trim()}%`]);
    }

    const connections = await db.getDocList(doctype['SSH Connection'], {
      fields: [
        'name',
        'display_name',
        'enabled',
        'host',
        'port',
        'username',
        'auth_method',
        'host_key_verification',
        'host_key_fingerprint',
        'host_key_type',
        'last_tested_on',
        'last_test_status',
        'last_error',
        'modified',
      ],
      filters: filters.length > 0 ? (filters as never) : undefined,
      limit: limit + 1,
      ...(start > 0 && { limit_start: start }),
      orderBy: { field: 'modified', order: 'desc' },
    });

    const mappedConnections = connections as SSHConnectionDoc[];
    const hasMore = mappedConnections.length > limit;
    const items = hasMore ? mappedConnections.slice(0, limit) : mappedConnections;
    const total = await fetchPaginatedCount(page, items.length, doctype['SSH Connection'], filters);

    return {
      items,
      hasMore,
      total,
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching SSH connections');
    throw error;
  }
}

export async function getSSHConnection(name: string): Promise<SSHConnectionDoc> {
  try {
    const response = await db.getDoc(doctype['SSH Connection'], name);
    return response as SSHConnectionDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function createSSHConnection(data: Partial<SSHConnectionDoc>): Promise<SSHConnectionDoc> {
  try {
    const response = await db.createDoc(doctype['SSH Connection'], data);
    return response as SSHConnectionDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function updateSSHConnection(
  name: string,
  data: Partial<SSHConnectionDoc>
): Promise<SSHConnectionDoc> {
  try {
    const response = await db.updateDoc(doctype['SSH Connection'], name, data);
    return response as SSHConnectionDoc;
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function deleteSSHConnection(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['SSH Connection'], name);
  } catch (error) {
    handleFrappeError(error);
    throw error;
  }
}

export async function testSSHConnection(connectionName: string): Promise<SSHTestResult> {
  try {
    const response = await call.post('huf.huf.doctype.ssh_connection.ssh_connection.test_ssh_connection', {
      connection_name: connectionName,
    });
    return response.message as SSHTestResult;
  } catch (error) {
    handleFrappeError(error, 'Error testing SSH connection');
    throw error;
  }
}

export async function enrollHostKey(connectionName: string): Promise<SSHTestResult> {
  try {
    const response = await call.post('huf.huf.doctype.ssh_connection.ssh_connection.enroll_host_key', {
      connection_name: connectionName,
    });
    return response.message as SSHTestResult;
  } catch (error) {
    handleFrappeError(error, 'Error enrolling host key');
    throw error;
  }
}

export async function rotateSSHSecret(
  connectionName: string,
  authMethod: 'Password' | 'Private Key',
  secretData: { password?: string; privateKey?: string; passphrase?: string }
): Promise<{ success: boolean; name: string; auth_method: string }> {
  try {
    const response = await call.post('huf.huf.doctype.ssh_connection.ssh_connection.rotate_ssh_secret', {
      connection_name: connectionName,
      auth_method: authMethod,
      password: secretData.password,
      private_key: secretData.privateKey,
      private_key_passphrase: secretData.passphrase,
    });
    return response.message;
  } catch (error) {
    handleFrappeError(error, 'Error rotating SSH secret');
    throw error;
  }
}
