import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import type { AgentToolFunctionRef, AgentToolType } from '@/types/agent.types';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Fetch all available tool types from Frappe
 */
export async function getToolTypes(): Promise<AgentToolType[]> {
  try {
    const toolTypes = await db.getDocList(doctype['Agent Tool Type'], {
      fields: ['name', 'name1'],
      limit: 1000,
    });
    return toolTypes as AgentToolType[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching tool types');
  }
}

/**
 * Fetch all available tool functions from Frappe
 * Only fetches: name, description, and tool_type
 * Optionally filter by tool_type
 */
export async function getToolFunctions(toolTypeFilter?: string): Promise<AgentToolFunctionRef[]> {
  try {
    const options = {
      fields: ["name", "description", "tool_type"],
      limit: 1000,
      filters: [] as any,
    };
    if (toolTypeFilter && options.filters) {
      options.filters.push({ field: 'tool_type', operator: '=', value: toolTypeFilter });
    }

    const tools = await db.getDocList(doctype['Agent Tool Function'], options);
    return tools as AgentToolFunctionRef[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching tool functions');
  }
}

/**
 * Create a new Agent Tool Function document
 */
export async function createToolFunction(data: {
  tool_name: string;
  tool_type: string;
  types: string;
  description: string;
  reference_doctype?: string;
  agent?: string;
  function_path?: string;
  function_name?: string;
  pass_parameters_as_json?: boolean;
  provider_app?: string;
  base_url?: string;
  required_permission?: string;
  is_read_only?: boolean;
  allowed_for_guest?: boolean;
  parameters?: Array<{
    label: string;
    fieldname: string;
    type: string;
    required: boolean;
    description?: string;
    options?: string;
    child_table_name?: string;
  }>;
  http_headers?: Array<{
    key: string;
    value: string;
  }>;
}): Promise<AgentToolFunctionRef> {
  try {
    // Prepare data for Frappe
    const toolData: any = {
      tool_name: data.tool_name,
      tool_type: data.tool_type,
      types: data.types,
      description: data.description,
    };

    // Add optional fields
    if (data.reference_doctype) toolData.reference_doctype = data.reference_doctype;
    if (data.agent) toolData.agent = data.agent;
    if (data.function_path) toolData.function_path = data.function_path;
    if (data.function_name) toolData.function_name = data.function_name;
    if (data.provider_app) toolData.provider_app = data.provider_app;
    if (data.base_url) toolData.base_url = data.base_url;
    if (data.required_permission) toolData.required_permission = data.required_permission;
    
    // Boolean fields (convert to 0/1 for Frappe)
    toolData.is_read_only = data.is_read_only ? 1 : 0;
    toolData.allowed_for_guest = data.allowed_for_guest ? 1 : 0;
    toolData.pass_parameters_as_json = data.pass_parameters_as_json ? 1 : 0;

    // Handle child tables - Frappe expects arrays
    if (data.parameters && data.parameters.length > 0) {
      toolData.parameters = data.parameters.map((param) => ({
        label: param.label,
        fieldname: param.fieldname,
        type: param.type,
        required: param.required ? 1 : 0,
        description: param.description || '',
        options: param.options || '',
        child_table_name: param.child_table_name || '',
      }));
    }

    if (data.http_headers && data.http_headers.length > 0) {
      toolData.http_headers = data.http_headers.map((header) => ({
        key: header.key,
        value: header.value,
      }));
    }

    const newTool = await db.createDoc(doctype['Agent Tool Function'], toolData);
    return {
      name: newTool.name,
      tool_name: newTool.tool_name,
      description: newTool.description,
      types: newTool.types as any,
      tool_type: newTool.tool_type,
    };
  } catch (error) {
    handleFrappeError(error, 'Error creating tool function');
  }
}
