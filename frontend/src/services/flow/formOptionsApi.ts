import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/** A kind of record the "Create document" step may make. */
export interface CreateDocType {
  name: string;
  /** What people call it ("To-do" for ToDo). */
  label: string;
}

/** One field of a record a "Create document" step may fill in. */
export interface CreateDocField {
  fieldname: string;
  label: string;
  fieldtype: string;
  /** How to ask for it. */
  kind: 'text' | 'longtext' | 'number' | 'yesno' | 'date' | 'choice';
  required: boolean;
  options: string[];
}

/** A person who can be named as an approver. */
export interface FlowUser {
  name: string;
  /** Their sign-in address, the only other thing the server tells an editor about a person. */
  email?: string;
  full_name: string;
  /** True when the person holds one of the approver roles (absent when the server could not tell). */
  has_approver_role?: boolean;
  /** "Ada Lovelace (ada@example.com)" */
  label: string;
}

export interface CheckedUser {
  name: string;
  found: boolean;
  full_name: string;
}

export async function listCreateDocTypes(): Promise<CreateDocType[]> {
  try {
    const result = await call.post('huf.ai.flow.catalog.form_options_api.get_create_document_types', {});
    return (result.message as CreateDocType[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error loading the kinds of record');
  }
}

export async function listCreateDocFields(doctype: string): Promise<CreateDocField[]> {
  try {
    const result = await call.post('huf.ai.flow.catalog.form_options_api.get_create_document_fields', { doctype });
    return (result.message as CreateDocField[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error loading the fields');
  }
}

export async function searchFlowUsers(query: string): Promise<FlowUser[]> {
  try {
    const result = await call.post('huf.ai.flow.catalog.form_options_api.search_flow_users', { query });
    return (result.message as FlowUser[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error looking up people');
  }
}

export async function checkFlowUsers(users: string[]): Promise<CheckedUser[]> {
  try {
    const result = await call.post('huf.ai.flow.catalog.form_options_api.check_flow_users', { users });
    return (result.message as CheckedUser[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error checking people');
  }
}
