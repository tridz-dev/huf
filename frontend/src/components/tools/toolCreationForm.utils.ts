import * as z from 'zod';
import type { ParameterData } from './ParameterCard';
import type { ToolFormData } from '@/types/toolTemplate.types';
import type { ToolType } from '@/types/agent.types';
import { getDocTypeMeta } from '@/services/agentApi';

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
    auto_add_to_agent: z.boolean().optional(),
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
  auto_add_to_agent: initialData?.auto_add_to_agent ?? true,
});

export function parseParameterOptions(value: string): string[] {
  const trimmed = value.trim();
  if (!trimmed) return [];

  if (value.includes('\n')) {
    return value.split('\n').map((item) => item.trim()).filter(Boolean);
  }

  if (value.includes(',')) {
    return value.split(',').map((item) => item.trim()).filter(Boolean);
  }

  return [trimmed];
}

export function normalizeParameterOptionsValue(value: string): string {
  return parseParameterOptions(value).join('\n');
}

interface DocTypeField {
  fieldname?: string;
  label?: string;
  fieldtype?: string;
  reqd?: 0 | 1 | boolean;
  options?: string;
  hidden?: 0 | 1 | boolean;
}

export const buildMissingMandatoryParameters = (
  metaFields: DocTypeField[],
  currentParams: ParameterData[]
): ParameterData[] => {
  const existingFieldnames = new Set(currentParams.map((p) => p.fieldname));

  return metaFields
    .filter((df) => {
      if (!df?.fieldname) return false;
      if (!df.reqd) return false;
      if (SYSTEM_IGNORE_FIELDS.has(df.fieldname)) return false;
      if (df.fieldtype === 'Table') return false;
      if (existingFieldnames.has(df.fieldname)) return false;
      return true;
    })
    .map((df) => ({
      label: df.label || df.fieldname || '',
      fieldname: df.fieldname || '',
      type: mapFieldtypeToParamType(df.fieldtype),
      required: true,
      description: '',
      options: df.fieldtype === 'Select' ? normalizeParameterOptionsValue(df.options || '') : '',
      child_table_name: '',
    }));
};

export const SKIP_LAYOUT_FIELD_TYPES = new Set([
  'Section Break',
  'Column Break',
  'Tab Break',
  'HTML',
  'Button',
  'Image',
  'Fold',
  'Table',
]);

export interface DocTypeFieldSelectOption {
  value: string;
  label: string;
  group?: string;
}

export interface DocTypeMeta {
  fields?: DocTypeField[];
}

export interface DocTypeFieldCatalog {
  parentMeta: DocTypeMeta;
  childTableMetas: Record<string, DocTypeMeta>;
}

export function getParameterFieldKey(param: Pick<ParameterData, 'fieldname' | 'child_table_name'>): string {
  if (param.child_table_name) {
    return `${param.child_table_name}:${param.fieldname}`;
  }
  return param.fieldname;
}

function isSelectableField(df: DocTypeField, includeTable = false): boolean {
  if (!df.fieldname) return false;
  if (df.hidden) return false;
  const skipTypes = includeTable
    ? [...SKIP_LAYOUT_FIELD_TYPES].filter((type) => type !== 'Table')
    : [...SKIP_LAYOUT_FIELD_TYPES];
  return !skipTypes.includes(df.fieldtype || '');
}

export function buildDocTypeFieldSelectOptions(
  parentMeta: DocTypeMeta,
  childTableMetas: Record<string, DocTypeMeta>,
  currentParams: ParameterData[]
): DocTypeFieldSelectOption[] {
  const currentFields = new Set(currentParams.map(getParameterFieldKey));
  const options: DocTypeFieldSelectOption[] = [];
  const parentFields = parentMeta.fields || [];

  parentFields.forEach((df) => {
    if (!isSelectableField(df)) return;
    if (currentFields.has(df.fieldname || '')) return;

    const label = df.label || df.fieldname || '';
    options.push({
      value: df.fieldname || '',
      label: `${label} (${df.fieldname})`,
      group: 'Parent Fields',
    });
  });

  parentFields
    .filter((df) => df.fieldtype === 'Table' && df.options && df.fieldname)
    .forEach((tableDf) => {
      const childMeta = childTableMetas[tableDf.fieldname || ''];
      if (!childMeta?.fields) return;

      childMeta.fields.forEach((cdf) => {
        if (!isSelectableField(cdf, true)) return;

        const itemKey = `${tableDf.fieldname}:${cdf.fieldname}`;
        if (currentFields.has(itemKey)) return;

        const tableLabel = tableDf.label || tableDf.fieldname || '';
        const childLabel = cdf.label || cdf.fieldname || '';
        options.push({
          value: itemKey,
          label: `${tableLabel} > ${childLabel} (${cdf.fieldname})`,
          group: 'Child Table Fields',
        });
      });
    });

  return options;
}

function fieldToParameter(df: DocTypeField, childTableName = ''): ParameterData {
  return {
    label: df.label || df.fieldname || '',
    fieldname: df.fieldname || '',
    type: mapFieldtypeToParamType(df.fieldtype),
    required: false,
    description: '',
    options: df.fieldtype === 'Select' ? normalizeParameterOptionsValue(df.options || '') : '',
    child_table_name: childTableName,
  };
}

export function buildParametersFromSelectedFields(
  selectedKeys: string[],
  parentMeta: DocTypeMeta,
  childTableMetas: Record<string, DocTypeMeta>
): ParameterData[] {
  const parentFields = parentMeta.fields || [];
  const params: ParameterData[] = [];

  selectedKeys.forEach((key) => {
    if (key.includes(':')) {
      const [tableFieldname, childFieldname] = key.split(':');
      const tableDf = parentFields.find((f) => f.fieldname === tableFieldname);
      if (!tableDf) return;

      const childMeta = childTableMetas[tableFieldname];
      const childDf = childMeta?.fields?.find((f) => f.fieldname === childFieldname);
      if (childDf) {
        params.push(fieldToParameter(childDf, tableFieldname));
      }
      return;
    }

    const df = parentFields.find((f) => f.fieldname === key);
    if (df) {
      params.push(fieldToParameter(df));
    }
  });

  return params;
}

export async function loadDocTypeFieldCatalog(doctypeName: string): Promise<DocTypeFieldCatalog> {
  const parentMeta = (await getDocTypeMeta(doctypeName)) as DocTypeMeta;
  const parentFields = parentMeta.fields || [];

  const childTableFields = parentFields.filter(
    (df) => df.fieldtype === 'Table' && df.options && df.fieldname
  );

  const childMetaEntries = await Promise.all(
    childTableFields.map(async (tableDf) => {
      const childDoctype = tableDf.options || '';
      const childMeta = (await getDocTypeMeta(childDoctype)) as DocTypeMeta;
      return [tableDf.fieldname || '', childMeta] as const;
    })
  );

  const childTableMetas: Record<string, DocTypeMeta> = {};
  childMetaEntries.forEach(([tableFieldname, meta]) => {
    childTableMetas[tableFieldname] = meta;
  });

  return { parentMeta, childTableMetas };
}
