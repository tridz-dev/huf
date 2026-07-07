import * as z from 'zod';
import type { ParameterData } from './ParameterCard';
import type { ToolFormData } from '@/types/toolTemplate.types';
import type { ToolType } from '@/types/agent.types';

const SYSTEM_IGNORE_FIELDS = new Set([
  'name',
  'owner',
  'creation',
  'modified',
  'modified_by',
  'docstatus',
]);

const mapFieldtypeToParamType = (fieldtype?: string): ParameterData['type'] => {
  if (!fieldtype) return 'string';
  if (['Int', 'Integer', 'Small Int', 'Long'].includes(fieldtype)) return 'integer';
  if (['Float', 'Currency', 'Percent', 'Duration'].includes(fieldtype)) return 'number';
  if (fieldtype === 'Check') return 'boolean';
  if (fieldtype === 'Table') return 'array';
  return 'string';
};

export const createToolFormSchema = (availableToolTypes: ToolType[]) => {
  const toolTypesEnum = z.enum(availableToolTypes as [ToolType, ...ToolType[]]);

  return z.object({
    tool_name: z.string().min(1, 'Tool name is required').max(128, 'Tool name must be at most 128 characters'),
    tool_type: z.string().min(1, 'Tool category is required'),
    types: toolTypesEnum,
    description: z.string().min(1, 'Description is required'),
    reference_doctype: z.string().optional(),
    agent: z.string().optional(),
    function_path: z.string().optional(),
    function_name: z.string().optional(),
    pass_parameters_as_json: z.boolean().optional(),
    provider_app: z.string().optional(),
    base_url: z
      .string()
      .refine((val) => !val || /^https?:\/\/.+/.test(val), {
        message: 'Must be a valid URL starting with http:// or https://',
      })
      .optional(),
    required_permission: z.enum(['read', 'write', 'create', 'delete', 'submit', 'cancel']).optional(),
    is_read_only: z.boolean().optional(),
    allowed_for_guest: z.boolean().optional(),
    parameters: z.array(z.any()).optional(),
    http_headers: z
      .array(
        z.object({
          key: z.string(),
          value: z.string(),
        })
      )
      .optional(),
  });
};

// Tool types that require a reference_doctype field
const REFERENCE_DOCTYPE_ALLOWED_TYPES: ToolType[] = [
  'Get Document',
  'Get Multiple Documents',
  'Get List',
  'Create Document',
  'Create Multiple Documents',
  'Update Document',
  'Update Multiple Documents',
  'Delete Document',
  'Delete Multiple Documents',
  'Submit Document',
  'Cancel Document',
  'Get Amended Document',
  'Attach File to Document',
  'Get Report Result',
  'Get Value',
  'Set Value',
];

export const shouldShowField = (fieldName: string, types: ToolType): boolean => {
  switch (fieldName) {
    case 'reference_doctype':
      return REFERENCE_DOCTYPE_ALLOWED_TYPES.includes(types);
    case 'agent':
      return types === 'Run Agent';
    case 'function_path':
      return ['Custom Function', 'App Provided'].includes(types);
    case 'function_name':
      return types === 'Client Side Tool';
    case 'pass_parameters_as_json':
      return types === 'Custom Function' || types === 'Client Side Tool';
    case 'provider_app':
      return types === 'App Provided';
    case 'base_url':
    case 'http_headers':
      return ['GET', 'POST'].includes(types);
    default:
      return true;
  }
};

export const getDefaultToolFormValues = (
  initialData: Partial<ToolFormData> | null | undefined,
  fallbackType: ToolType
): ToolFormData => ({
  tool_name: initialData?.tool_name || '',
  tool_type: initialData?.tool_type || '',
  types: (initialData?.types || fallbackType) as ToolType,
  description: initialData?.description || '',
  reference_doctype: initialData?.reference_doctype,
  agent: initialData?.agent,
  function_path: initialData?.function_path,
  function_name: initialData?.function_name,
  pass_parameters_as_json: initialData?.pass_parameters_as_json || false,
  provider_app: initialData?.provider_app,
  base_url: initialData?.base_url,
  required_permission: initialData?.required_permission,
  is_read_only: initialData?.is_read_only || false,
  allowed_for_guest: initialData?.allowed_for_guest || false,
  parameters: initialData?.parameters || [],
  http_headers: initialData?.http_headers || [],
});

export const buildMissingMandatoryParameters = (
  metaFields: any[],
  currentParams: ParameterData[]
): ParameterData[] => {
  const existingFieldnames = new Set(currentParams.map((p) => p.fieldname));

  return metaFields
    .filter((df: any) => {
      if (!df?.fieldname) return false;
      if (!df.reqd) return false;
      if (SYSTEM_IGNORE_FIELDS.has(df.fieldname)) return false;
      if (df.fieldtype === 'Table') return false;
      if (existingFieldnames.has(df.fieldname)) return false;
      return true;
    })
    .map((df: any) => ({
      label: df.label || df.fieldname,
      fieldname: df.fieldname,
      type: mapFieldtypeToParamType(df.fieldtype),
      required: true,
      description: '',
      options: df.fieldtype === 'Select' ? df.options || '' : '',
      child_table_name: '',
    }));
};
