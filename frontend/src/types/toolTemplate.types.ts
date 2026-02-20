import type { ToolType } from './agent.types';
import type { ParameterData } from '@/components/tools/ParameterCard';
import type { HttpHeaderData } from '@/components/tools/HttpHeaderCard';

export type ToolTemplate = {
  id: string;
  name: string;
  description: string;
  icon: string;
  toolTypes: ToolType[];
};

export type ToolTemplateConfig = {
  templates: ToolTemplate[];
};

export type ToolFormData = {
  // Core fields
  tool_name: string;
  tool_type: string;
  types: ToolType;
  description: string;
  
  // Conditional fields based on types
  reference_doctype?: string;
  agent?: string;
  function_path?: string;
  function_name?: string;
  pass_parameters_as_json?: boolean;
  provider_app?: string;
  base_url?: string;
  
  // Optional fields
  required_permission?: 'read' | 'write' | 'create' | 'delete' | 'submit' | 'cancel';
  is_read_only?: boolean;
  allowed_for_guest?: boolean;
  
  // Child tables
  parameters?: ParameterData[];
  http_headers?: HttpHeaderData[];
};
