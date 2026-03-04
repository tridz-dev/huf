import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MeResponse {
  user: string;
  full_name: string;
  huf_role: string | null;
  capabilities: string[];
}

export interface HufUser {
  user: string;
  email: string;
  full_name: string;
  huf_role: string;
  enabled: number;
  invited_by: string;
  invited_on: string;
}

export interface HufRole {
  role_name: string;
  description: string;
  is_system_role: number;
  frappe_role: string;
  capabilities: string[];
}

// ---------------------------------------------------------------------------
// /huf/me — identity + capabilities
// ---------------------------------------------------------------------------

export async function getMe(): Promise<MeResponse> {
  try {
    const res = await call.get('huf.permissions.get_me');
    return res.message as MeResponse;
  } catch (error) {
    handleFrappeError(error, 'Error loading user permissions');
    // Return a safe fallback so the UI doesn't crash on error
    return { user: '', full_name: '', huf_role: null, capabilities: [] };
  }
}

// ---------------------------------------------------------------------------
// User management
// ---------------------------------------------------------------------------

export async function getUsers(): Promise<HufUser[]> {
  try {
    const res = await call.get('huf.ai.permissions_api.get_users');
    return (res.message as HufUser[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching users');
    return [];
  }
}

export async function inviteUser(
  email: string,
  full_name: string,
  huf_role: string,
): Promise<HufUser | null> {
  try {
    const res = await call.post('huf.ai.permissions_api.invite_user', {
      email,
      full_name,
      huf_role,
    });
    return res.message as HufUser;
  } catch (error) {
    handleFrappeError(error, 'Error inviting user');
    return null;
  }
}

export async function updateUserRole(user: string, huf_role: string): Promise<HufUser | null> {
  try {
    const res = await call.post('huf.ai.permissions_api.update_user_role', { user, huf_role });
    return res.message as HufUser;
  } catch (error) {
    handleFrappeError(error, 'Error updating user role');
    return null;
  }
}

export async function setUserEnabled(user: string, enabled: boolean): Promise<HufUser | null> {
  try {
    const res = await call.post('huf.ai.permissions_api.set_user_enabled', {
      user,
      enabled: enabled ? 1 : 0,
    });
    return res.message as HufUser;
  } catch (error) {
    handleFrappeError(error, 'Error updating user status');
    return null;
  }
}

// ---------------------------------------------------------------------------
// Role management
// ---------------------------------------------------------------------------

export async function getHufRoles(): Promise<HufRole[]> {
  try {
    const res = await call.get('huf.ai.permissions_api.get_huf_roles');
    return (res.message as HufRole[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching roles');
    return [];
  }
}

export async function getCapabilitiesCatalogue(): Promise<Record<string, string>> {
  try {
    const res = await call.get('huf.ai.permissions_api.get_capabilities_catalogue');
    return (res.message as Record<string, string>) ?? {};
  } catch (error) {
    handleFrappeError(error, 'Error fetching capabilities');
    return {};
  }
}

export async function createHufRole(
  role_name: string,
  description: string,
  capabilities: string[],
): Promise<HufRole | null> {
  try {
    const res = await call.post('huf.ai.permissions_api.create_huf_role', {
      role_name,
      description,
      capabilities,
    });
    return res.message as HufRole;
  } catch (error) {
    handleFrappeError(error, 'Error creating role');
    return null;
  }
}

export async function updateHufRole(
  role_name: string,
  capabilities: string[],
  description?: string,
): Promise<HufRole | null> {
  try {
    const res = await call.post('huf.ai.permissions_api.update_huf_role', {
      role_name,
      capabilities,
      description,
    });
    return res.message as HufRole;
  } catch (error) {
    handleFrappeError(error, 'Error updating role');
    return null;
  }
}
