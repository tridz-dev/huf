import { call, db } from '@/lib/frappe-sdk';
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
      fields: ["name", "tool_name", "description", "tool_type", "types", "reference_doctype"],
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
 * Fetch specific tool functions by their names
 * More efficient than fetching all tools and filtering
 */
export async function getToolFunctionsByName(toolNames: string[]): Promise<AgentToolFunctionRef[]> {
  try {
    if (toolNames.length === 0) return [];
    
    const tools = await db.getDocList(doctype['Agent Tool Function'], {
      fields: ["name", "tool_name", "description", "tool_type", "types", "reference_doctype"],
      filters: [["name", "in", toolNames]],
      limit: 1000,
    });
    return tools as AgentToolFunctionRef[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching tool functions by name');
    return [];
  }
}

/**
 * Fetch a single Agent Tool Function by name with all fields including child tables
 */
export async function getToolFunction(name: string): Promise<any> {
  try {
    const tool = await db.getDoc(doctype['Agent Tool Function'], name);
    
    // Convert child table data to our format (add IDs for React keys)
    if (tool.parameters && Array.isArray(tool.parameters)) {
      tool.parameters = tool.parameters.map((param: any, index: number) => ({
        id: param.name || `param-${index}`, // Use Frappe name or generate ID
        label: param.label || '',
        fieldname: param.fieldname || '',
        type: param.type || 'string',
        required: param.required === 1 || param.required === true,
        description: param.description || '',
        options: param.options || '',
        child_table_name: param.child_table_name || '',
      }));
    }
    
    if (tool.http_headers && Array.isArray(tool.http_headers)) {
      tool.http_headers = tool.http_headers.map((header: any, index: number) => ({
        id: header.name || `header-${index}`, // Use Frappe name or generate ID
        key: header.key || '',
        value: header.value || '',
      }));
    }
    
    return tool;
  } catch (error) {
    handleFrappeError(error, 'Error fetching tool function');
  }
}

/**
 * Update an existing Agent Tool Function document
 */
export async function updateToolFunction(name: string, data: {
  tool_name?: string;
  tool_type?: string;
  types?: string;
  description?: string;
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
    const toolData: any = {};

    // Only include fields that are provided
    if (data.tool_name !== undefined) toolData.tool_name = data.tool_name;
    if (data.tool_type !== undefined) toolData.tool_type = data.tool_type;
    if (data.types !== undefined) toolData.types = data.types;
    if (data.description !== undefined) toolData.description = data.description;
    if (data.reference_doctype !== undefined) toolData.reference_doctype = data.reference_doctype;
    if (data.agent !== undefined) toolData.agent = data.agent;
    if (data.function_path !== undefined) toolData.function_path = data.function_path;
    if (data.function_name !== undefined) toolData.function_name = data.function_name;
    if (data.provider_app !== undefined) toolData.provider_app = data.provider_app;
    if (data.base_url !== undefined) toolData.base_url = data.base_url;
    if (data.required_permission !== undefined) toolData.required_permission = data.required_permission;
    
    // Boolean fields (convert to 0/1 for Frappe)
    if (data.is_read_only !== undefined) toolData.is_read_only = data.is_read_only ? 1 : 0;
    if (data.allowed_for_guest !== undefined) toolData.allowed_for_guest = data.allowed_for_guest ? 1 : 0;
    if (data.pass_parameters_as_json !== undefined) toolData.pass_parameters_as_json = data.pass_parameters_as_json ? 1 : 0;

    // Handle child tables - Frappe expects arrays
    if (data.parameters !== undefined) {
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

    if (data.http_headers !== undefined) {
      toolData.http_headers = data.http_headers.map((header) => ({
        key: header.key,
        value: header.value,
      }));
    }

    const updatedTool = await db.updateDoc(doctype['Agent Tool Function'], name, toolData);
    return {
      name: updatedTool.name,
      tool_name: updatedTool.tool_name,
      description: updatedTool.description,
      types: updatedTool.types as any,
      tool_type: updatedTool.tool_type,
    };
  } catch (error) {
    handleFrappeError(error, 'Error updating tool function');
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

/**
 * Get agents that use a specific tool
 * @param toolName - The name of the Agent Tool Function document
 * @returns Array of agent document names (name field) that use this tool
 */
export async function getAgentsUsingTool(toolName: string): Promise<string[]> {
  try {
    // Filter by child table field using the DocType and fieldname array format
    const agents = await db.getDocList(doctype['Agent'], {
      fields: ['name', 'agent_name'],
      filters: [['Agent Tool', 'tool', '=', toolName] as any],
      limit: 1000,
    });
    // Return document names for consistent comparison
    return agents.map((agent: any) => agent.name);
  } catch (error) {
    handleFrappeError(error, 'Error fetching agents using tool');
    return [];
  }
}

/**
 * Fetch parameters from a python function path (for Custom Function tools)
 */
export async function fetchToolParametersFromCode(functionPath: string): Promise<{
  parameters: Array<{
    label: string;
    fieldname: string;
    type: string;
    required: boolean | number;
  }>;
  pass_parameters_as_json?: boolean | number;
}> {
  try {
    const result = await call.post(
      'huf.huf.doctype.agent_tool_function.agent_tool_function.fetch_tool_parameters_from_code',
      { function_path: functionPath }
    );
    return (result?.message || result) as {
      parameters: Array<{
        label: string;
        fieldname: string;
        type: string;
        required: boolean | number;
      }>;
      pass_parameters_as_json?: boolean | number;
    };
  } catch (error) {
    handleFrappeError(error, 'Error fetching parameters from function code');
  }
}
