import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

export interface AIProviderConnectionDoc {
  name: string;
  connection_name: string;
  user: string;
  provider: string;
  adapter_type: string;
  auth_status: string;
  auth_method?: string;
  is_active: 0 | 1;
  eligible_models?: string;
  account_email?: string;
  account_id?: string;
  expires_at?: string;
  modified?: string;
}

export interface AuthMethod {
  method: string;
  type: string;
  label: string;
}

export interface ConnectionListItem extends AIProviderConnectionDoc {
  auth_methods: AuthMethod[];
  is_expired: boolean;
}

export interface StartAuthorizationResult {
  auth_url?: string;
  user_code?: string;
  verification_uri?: string;
  verification_uri_complete?: string;
  device_code?: string;
  expires_in?: number;
  interval?: number;
  instructions?: string;
}

export interface CompleteAuthorizationResult {
  status: string;
  account_email?: string;
  expires_in?: number;
}

export async function getConnections(provider?: string): Promise<ConnectionListItem[]> {
  try {
    const response = (await call.post('huf.huf.doctype.ai_provider_connection.ai_provider_connection.get_subscription_connections', {
      provider,
    })) as { message?: ConnectionListItem[] };
    return response?.message || [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching subscription connections');
    return [];
  }
}

export async function getAuthMethods(adapterType: string): Promise<AuthMethod[]> {
  try {
    const response = (await call.post('huf.huf.doctype.ai_provider_connection.ai_provider_connection.get_subscription_auth_methods', {
      adapter_type: adapterType,
    })) as { message?: AuthMethod[] };
    return response?.message || [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching auth methods');
    return [];
  }
}

export async function startAuthorization(
  connectionName: string,
  mode: string,
  redirectUri?: string,
): Promise<StartAuthorizationResult> {
  try {
    const response = (await call.post('huf.huf.doctype.ai_provider_connection.ai_provider_connection.start_subscription_authorization', {
      connection_name: connectionName,
      mode,
      redirect_uri: redirectUri,
    })) as { message?: StartAuthorizationResult };
    return response?.message || {};
  } catch (error) {
    handleFrappeError(error, 'Error starting authorization');
    throw error;
  }
}

export async function completeAuthorization(
  connectionName: string,
  payload?: Record<string, unknown>,
): Promise<CompleteAuthorizationResult> {
  try {
    const response = (await call.post('huf.huf.doctype.ai_provider_connection.ai_provider_connection.complete_subscription_authorization', {
      connection_name: connectionName,
      payload: payload || {},
    })) as { message?: CompleteAuthorizationResult };
    return response?.message || { status: 'unknown' };
  } catch (error) {
    handleFrappeError(error, 'Error completing authorization');
    throw error;
  }
}

export async function revokeAuthorization(connectionName: string): Promise<{ success: boolean; auth_status: string }> {
  try {
    const response = (await call.post('huf.huf.doctype.ai_provider_connection.ai_provider_connection.revoke_subscription_authorization', {
      connection_name: connectionName,
    })) as { message?: { success: boolean; auth_status: string } };
    return response?.message || { success: false, auth_status: 'Error' };
  } catch (error) {
    handleFrappeError(error, 'Error revoking connection');
    throw error;
  }
}

export async function getConnection(name: string): Promise<AIProviderConnectionDoc | null> {
  try {
    const doc = await db.getDoc(doctype['AI Provider Connection'], name);
    return doc as AIProviderConnectionDoc;
  } catch (error) {
    handleFrappeError(error, `Error fetching connection ${name}`);
    return null;
  }
}

export interface CreateConnectionInput {
  connection_name: string;
  user: string;
  provider: string;
  adapter_type: string;
  auth_method: string;
  eligible_models?: string;
  is_active?: 0 | 1;
}

export async function createConnection(data: CreateConnectionInput): Promise<AIProviderConnectionDoc> {
  try {
    const doc = await db.createDoc(doctype['AI Provider Connection'], {
      ...data,
      is_active: data.is_active ?? 1,
      auth_status: 'Unlinked',
    });
    return doc as AIProviderConnectionDoc;
  } catch (error) {
    handleFrappeError(error, 'Error creating connection');
    throw error;
  }
}

export async function updateConnection(
  name: string,
  data: Partial<AIProviderConnectionDoc>,
): Promise<AIProviderConnectionDoc> {
  try {
    await db.updateDoc(doctype['AI Provider Connection'], name, data);
    const updated = await db.getDoc(doctype['AI Provider Connection'], name);
    return updated as AIProviderConnectionDoc;
  } catch (error) {
    handleFrappeError(error, `Error updating connection ${name}`);
    throw error;
  }
}

export async function deleteConnection(name: string): Promise<void> {
  try {
    await db.deleteDoc(doctype['AI Provider Connection'], name);
  } catch (error) {
    handleFrappeError(error, `Error deleting connection ${name}`);
    throw error;
  }
}
