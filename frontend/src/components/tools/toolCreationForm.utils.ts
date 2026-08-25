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
    description: z.string(),
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

// ---------------------------------------------------------------------------
// Document Operation auto-derivation
// ---------------------------------------------------------------------------

/** Verbs that operate on a reference DocType and support auto-derivation. */
export const DOCUMENT_OPERATION_TYPES: ToolType[] = [
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
];

export const isDocumentOperationType = (types?: string | null): boolean =>
  !!types && (DOCUMENT_OPERATION_TYPES as string[]).includes(types);

export const READ_ONLY_OPERATION_TYPES: ToolType[] = [
  'Get Document',
  'Get Multiple Documents',
  'Get List',
  'Get Amended Document',
];

/** "Sales Order" -> "sales_order" */
export function slugifyDoctypeName(doctype: string): string {
  return doctype
    .trim()
    .replace(/['"]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
}

const OPERATION_VERB_PREFIX: Record<string, string> = {
  'Get Document': 'get',
  'Get Multiple Documents': 'get_multiple',
  'Get List': 'get_list',
  'Create Document': 'create',
  'Create Multiple Documents': 'create_multiple',
  'Update Document': 'update',
  'Update Multiple Documents': 'update_multiple',
  'Delete Document': 'delete',
  'Delete Multiple Documents': 'delete_multiple',
  'Submit Document': 'submit',
  'Cancel Document': 'cancel',
  'Get Amended Document': 'get_amended',
};

const OPERATION_DESCRIPTION: Record<string, string> = {
  'Get Document': 'Fetch a single {dt} document by its ID (or matching field filters).',
  'Get Multiple Documents': 'Fetch multiple {dt} documents by their IDs.',
  'Get List': 'Fetch a list of {dt} documents, optionally filtered by field values.',
  'Create Document': 'Create a new {dt} document.',
  'Create Multiple Documents': 'Create multiple {dt} documents in one call.',
  'Update Document': 'Update fields on an existing {dt} document.',
  'Update Multiple Documents': 'Update multiple {dt} documents in one call.',
  'Delete Document': 'Delete a {dt} document by its ID.',
  'Delete Multiple Documents': 'Delete multiple {dt} documents by their IDs.',
  'Submit Document': 'Submit a {dt} document by its ID.',
  'Cancel Document': 'Cancel a submitted {dt} document by its ID.',
  'Get Amended Document': 'Get the amended version of a cancelled {dt} document.',
};

const OPERATION_PERMISSION: Record<string, 'read' | 'write' | 'create' | 'delete' | 'submit' | 'cancel'> = {
  'Get Document': 'read',
  'Get Multiple Documents': 'read',
  'Get List': 'read',
  'Create Document': 'create',
  'Create Multiple Documents': 'create',
  'Update Document': 'write',
  'Update Multiple Documents': 'write',
  'Delete Document': 'delete',
  'Delete Multiple Documents': 'delete',
  'Submit Document': 'submit',
  'Cancel Document': 'cancel',
  'Get Amended Document': 'read',
};

export interface DocumentOperationDefaults {
  toolName: string;
  description: string;
  isReadOnly: boolean;
  requiredPermission: 'read' | 'write' | 'create' | 'delete' | 'submit' | 'cancel';
  defaultParameters: ParameterData[];
}

const makeParam = (
  fieldname: string,
  type: ParameterData['type'],
  required: boolean,
  description: string,
  label?: string
): ParameterData => ({
  label: label || fieldname,
  fieldname,
  type,
  required,
  description,
  options: '',
  child_table_name: '',
});

/**
 * Derive sensible defaults for a Document Operation tool once verb + DocType
 * are known. Default parameters mirror what the backend handler for each verb
 * expects; verbs whose schema is fully auto-generated server-side
 * (e.g. Get List's filters/fields/limit wrapper) get no table rows so the
 * saved parameters table does not conflict with the generated schema.
 */
export function deriveDocumentOperationDefaults(
  verb: ToolType,
  doctype: string
): DocumentOperationDefaults | null {
  if (!isDocumentOperationType(verb) || !doctype) return null;

  const slug = slugifyDoctypeName(doctype);
  const prefix = OPERATION_VERB_PREFIX[verb] || 'tool';
  const description = (OPERATION_DESCRIPTION[verb] || '{verb} operation on {dt} documents.')
    .replace('{dt}', doctype)
    .replace('{verb}', verb);

  let defaultParameters: ParameterData[] = [];
  switch (verb) {
    case 'Get Document':
      defaultParameters = [
        makeParam('document_id', 'string', false, `The ID of the ${doctype} to get (optional if other filters given)`, 'Document ID'),
      ];
      break;
    case 'Get Multiple Documents':
      defaultParameters = [
        makeParam('document_ids', 'array', true, `The IDs of the ${doctype} documents to get`, 'Document IDs'),
      ];
      break;
    case 'Get List':
      // filters/fields/limit are auto-generated by the backend schema; the
      // parameter table only adds filter hints, so leave it empty by default.
      defaultParameters = [];
      break;
    case 'Create Document':
    case 'Create Multiple Documents':
      // Mandatory DocType fields are appended separately from DocType meta.
      defaultParameters = [];
      break;
    case 'Update Document':
    case 'Update Multiple Documents':
      defaultParameters = [
        makeParam('document_id', 'string', true, `The ID of the ${doctype} to update`, 'Document ID'),
      ];
      break;
    case 'Delete Document':
      defaultParameters = [
        makeParam('document_id', 'string', true, `The ID of the ${doctype} to delete`, 'Document ID'),
      ];
      break;
    case 'Delete Multiple Documents':
      defaultParameters = [
        makeParam('document_ids', 'array', true, `The IDs of the ${doctype} documents to delete`, 'Document IDs'),
      ];
      break;
    case 'Submit Document':
      defaultParameters = [
        makeParam('document_id', 'string', true, `The ID of the ${doctype} to submit`, 'Document ID'),
      ];
      break;
    case 'Cancel Document':
      defaultParameters = [
        makeParam('document_id', 'string', true, `The ID of the ${doctype} to cancel`, 'Document ID'),
      ];
      break;
    case 'Get Amended Document':
      defaultParameters = [
        makeParam('document_id', 'string', true, `The ID of the ${doctype} to get the amended document for`, 'Document ID'),
      ];
      break;
  }

  return {
    toolName: `${prefix}_${slug}`,
    description,
    isReadOnly: READ_ONLY_OPERATION_TYPES.includes(verb),
    requiredPermission: OPERATION_PERMISSION[verb] || 'read',
    defaultParameters,
  };
}

// ---------------------------------------------------------------------------
// Default Tool Category per creation template
// ---------------------------------------------------------------------------

/** Fallback category when a template has no specific mapping. */
export const FALLBACK_TOOL_CATEGORY = 'Miscellaneous';

/**
 * Default Tool Category (Agent Tool Type) per creation template.
 * Keys are the template ids from frontend/src/config/toolTemplates.json
 * (the five "Create New" picker cards). Values must match the curated
 * categories seeded by sync_default_tool_categories() in huf/install.py.
 */
const TEMPLATE_DEFAULT_CATEGORY: Record<string, string> = {
  document_operation: 'Data Operations',
  notification: 'Automation & Workflow',
  external_api: 'Integrations',
  platform_utility: 'AI & Generation',
  run_agent: 'Automation & Workflow',
  custom_function: 'Automation & Workflow',
};

export function getDefaultToolCategory(templateId?: string | null): string {
  return (templateId && TEMPLATE_DEFAULT_CATEGORY[templateId]) || FALLBACK_TOOL_CATEGORY;
}

/**
 * Build the full function definition schema, mirroring the backend
 * (`AgentToolFunction.prepare_function_params`) for Document Operation verbs
 * and falling back to the parameter-table schema for everything else.
 */
export function buildFunctionDefinition(args: {
  toolName: string;
  description: string;
  types?: string | null;
  referenceDoctype?: string | null;
  parameters: ParameterData[];
}): Record<string, unknown> {
  const { toolName, description, types, referenceDoctype, parameters } = args;

  const functionDef: Record<string, unknown> = {
    name: toolName || 'untitled_tool',
    description: description || 'No description provided.',
  };

  const dt = referenceDoctype || 'Document';
  const tableProperties: Record<string, Record<string, unknown>> = {};
  const tableRequired: string[] = [];
  parameters.forEach((param) => {
    if (!param.fieldname) return;
    const property: Record<string, unknown> = { type: param.type || 'string' };
    if (param.description) property.description = param.description;
    if (param.options?.trim()) property.enum = parseParameterOptions(param.options);
    tableProperties[param.fieldname] = property;
    if (param.required) tableRequired.push(param.fieldname);
  });

  const docIdProp = (action: string) => ({
    type: 'string',
    description: `The ID of the ${dt} to ${action}`,
  });
  const docIdsProp = (action: string) => ({
    type: 'array',
    items: { type: 'string' },
    description: `The IDs of the ${dt}s to ${action}`,
  });
  const fixedSchema = (properties: Record<string, unknown>, required: string[] = []) => ({
    type: 'object',
    properties,
    required,
    additionalProperties: false,
  });

  let schema: Record<string, unknown> | null = null;
  switch (types) {
    case 'Get Document':
      schema = fixedSchema({ document_id: docIdProp('get (optional)'), ...tableProperties });
      break;
    case 'Get Multiple Documents':
      schema = fixedSchema({ document_ids: docIdsProp('get') }, ['document_ids']);
      break;
    case 'Delete Document':
      schema = fixedSchema({ document_id: docIdProp('delete') }, ['document_id']);
      break;
    case 'Delete Multiple Documents':
      schema = fixedSchema({ document_ids: docIdsProp('delete') }, ['document_ids']);
      break;
    case 'Submit Document':
      schema = fixedSchema({ document_id: docIdProp('submit') }, ['document_id']);
      break;
    case 'Cancel Document':
      schema = fixedSchema({ document_id: docIdProp('cancel') }, ['document_id']);
      break;
    case 'Get Amended Document':
      schema = fixedSchema({ document_id: docIdProp('get the amended document for') }, ['document_id']);
      break;
    case 'Get List': {
      const filterProperties: Record<string, unknown> = {};
      parameters.forEach((param) => {
        if (!param.fieldname) return;
        filterProperties[param.fieldname] = {
          type: param.type || 'string',
          description: param.description || param.label || `Filter by ${param.fieldname}`,
        };
      });
      schema = {
        type: 'object',
        properties: {
          filters: {
            type: 'object',
            description: "Dictionary of filters. Example: {'status': 'New'}.",
            properties: filterProperties,
            additionalProperties: true,
          },
          fields: { type: 'array', items: { type: 'string' }, description: 'List of fields to retrieve.' },
          limit: { type: 'integer', description: 'Max records to return. Set to 0 to fetch ALL records.', default: 0 },
        },
        required: [],
        additionalProperties: false,
      };
      break;
    }
    case 'Update Document':
    case 'Update Multiple Documents': {
      const properties: Record<string, unknown> = {
        document_id: docIdProp('update'),
        ...tableProperties,
      };
      const required = Array.from(new Set(['document_id', ...tableRequired]));
      schema = { type: 'object', properties, required, additionalProperties: false };
      break;
    }
    default:
      break;
  }

  if (!schema) {
    schema = { type: 'object', properties: tableProperties };
    if (tableRequired.length > 0) schema.required = tableRequired;
  }

  functionDef.parameters = schema;
  return functionDef;
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
      try {
        const childMeta = (await getDocTypeMeta(childDoctype)) as DocTypeMeta;
        return [tableDf.fieldname || '', childMeta] as const;
      } catch (error) {
        // One child table's meta being denied/unavailable must not break
        // building the tool schema for every other field on this doctype.
        console.error(`Error loading child table meta for ${childDoctype}:`, error);
        return null;
      }
    })
  );

  const childTableMetas: Record<string, DocTypeMeta> = {};
  childMetaEntries.forEach((entry) => {
    if (!entry) return;
    const [tableFieldname, meta] = entry;
    childTableMetas[tableFieldname] = meta;
  });

  return { parentMeta, childTableMetas };
}
