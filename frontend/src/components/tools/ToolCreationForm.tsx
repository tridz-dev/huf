import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowLeft, Settings, Zap, Plus, Braces, Pencil, Trash2, Check, AlertTriangle, FlaskConical, ChevronDown, FileText, ShieldCheck, type LucideIcon } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Combobox } from '@/components/ui/combobox';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { linkRoutes } from '@/lib/link-routes';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ParameterCard, type ParameterData } from './ParameterCard';
import { HttpHeaderCard, type HttpHeaderData } from './HttpHeaderCard';
import { SelectDocTypeFieldsDialog } from './SelectDocTypeFieldsDialog';
import { TestToolDrawer } from './TestToolDrawer';
import type { ToolTemplate, ToolFormData } from '@/types/toolTemplate.types';
import type { AgentToolType, ToolType } from '@/types/agent.types';
import { getToolTypeDisplayLabel } from '@/data/ai';
import { getDocTypeMeta } from '@/services/agentApi';
import { fetchToolParametersFromCode, getAgentsUsingTool } from '@/services/toolApi';
import { toast } from 'sonner';
import { useToolCreationOptions } from './useToolCreationOptions';
import {
  buildFunctionDefinition,
  buildMissingMandatoryParameters,
  deriveDocumentOperationDefaults,
  getDefaultToolCategory,
  isDocumentOperationType,
  parseParameterOptions,
  createToolFormSchema,
  getDefaultToolFormValues,
  shouldShowField,
} from './toolCreationForm.utils';

type AutoFieldKey = 'tool_name' | 'tool_type' | 'description' | 'is_read_only' | 'required_permission' | 'parameters';
type AutoFieldState = Record<AutoFieldKey, 'auto' | 'edited'>;

// Consistent 2-level type scale: section headers (this) sit above field labels
// (FormLabel). One shared treatment for every zone header in the form.
function SectionHeader({ icon: Icon, title }: { icon?: LucideIcon; title: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      {Icon ? <Icon className="w-4 h-4 text-steel-soft shrink-0" /> : null}
      <h3 className="font-mono text-eyebrow uppercase text-steel">{title}</h3>
    </div>
  );
}

interface ToolCreationFormProps {
  template: ToolTemplate;
  toolTypes: AgentToolType[];
  onSubmit: (data: ToolFormData) => Promise<void>;
  onBack: () => void;
  loading?: boolean;
  initialData?: Partial<ToolFormData> | null;
  mode?: 'create' | 'edit';
  toolName?: string; // Document name for edit mode (to fetch shared usage)
  currentAgentName?: string; // Current agent name to exclude from shared usage count
}

export function ToolCreationForm({
  template,
  toolTypes,
  onSubmit,
  onBack,
  loading = false,
  initialData = null,
  mode = 'create',
  toolName,
  currentAgentName,
}: ToolCreationFormProps) {
  const formSchema = useMemo(() => createToolFormSchema(template.toolTypes), [template.toolTypes]);
  const { loadingData, docTypeOptions, agentOptions } = useToolCreationOptions();
  const [fetchingCodeParams, setFetchingCodeParams] = useState(false);
  const [showFieldSelector, setShowFieldSelector] = useState(false);
  const [editingParameterIndex, setEditingParameterIndex] = useState<number | null>(null);
  const [showParamsPreview, setShowParamsPreview] = useState(false);
  const [showTestDrawer, setShowTestDrawer] = useState(false);
  const [sharedUsedBy, setSharedUsedBy] = useState<string[]>([]);

  // Tracks whether derive-able fields still hold their auto-derived value.
  // Flips to 'edited' as soon as the user changes the field manually.
  const autoStateRef = useRef<AutoFieldState>({
    tool_name: mode === 'create' ? 'auto' : 'edited',
    tool_type: mode === 'create' ? 'auto' : 'edited',
    description: mode === 'create' ? 'auto' : 'edited',
    is_read_only: mode === 'create' ? 'auto' : 'edited',
    required_permission: mode === 'create' ? 'auto' : 'edited',
    parameters: mode === 'create' ? 'auto' : 'edited',
  });
  const [autoBadges, setAutoBadges] = useState<AutoFieldState>({ ...autoStateRef.current });
  const markEdited = (key: AutoFieldKey) => {
    if (autoStateRef.current[key] === 'edited') return;
    autoStateRef.current[key] = 'edited';
    setAutoBadges({ ...autoStateRef.current });
  };

  const defaultValues = useMemo(
    () => getDefaultToolFormValues(initialData, template.toolTypes[0] as ToolType),
    [initialData, template.toolTypes]
  );

  const form = useForm<ToolFormData>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  // Reset form when initialData changes (for edit mode)
  useEffect(() => {
    if (initialData && mode === 'edit') {
      form.reset(defaultValues);
    }
  }, [initialData, mode, form, defaultValues]);

  // Load shared tool usage data in edit mode
  useEffect(() => {
    if (mode === 'edit' && toolName) {
      getAgentsUsingTool(toolName)
        .then((agents) => {
          // Filter out the current agent from the list
          const filteredAgents = currentAgentName
            ? agents.filter((agent) => agent !== currentAgentName)
            : agents;
          setSharedUsedBy(filteredAgents);
        })
        .catch((error) => {
          console.error('Error loading tool usage:', error);
          setSharedUsedBy([]);
        });
    } else {
      setSharedUsedBy([]);
    }
  }, [mode, toolName, currentAgentName]);

  useEffect(() => {
    if (!loading) {
      setEditingParameterIndex(null);
      setShowParamsPreview(false);
    }
  }, [loading]);

  // Watch the types field to conditionally show fields
  const selectedType = useWatch({ control: form.control, name: 'types' });
  const selectedReferenceDoctype = useWatch({ control: form.control, name: 'reference_doctype' });
  const functionPathValue = useWatch({ control: form.control, name: 'function_path' });

  // Auto-derive tool_name / description / read-only / permission / default
  // parameters whenever a Document Operation verb + DocType are selected.
  // Fields the user has manually edited are never overwritten.
  useEffect(() => {
    if (mode !== 'create') return;

    // Default Tool Category from the creation template — applies to all five
    // tool-type bodies, independent of verb/DocType selection.
    if (autoStateRef.current.tool_type === 'auto') {
      const category = getDefaultToolCategory(template.id);
      if (form.getValues('tool_type') !== category) {
        form.setValue('tool_type', category, { shouldDirty: true });
      }
    }

    if (!selectedType || !selectedReferenceDoctype) return;

    const defaults = deriveDocumentOperationDefaults(selectedType, selectedReferenceDoctype);
    if (!defaults) return;

    if (autoStateRef.current.tool_name === 'auto') {
      form.setValue('tool_name', defaults.toolName, { shouldDirty: true });
    }
    if (autoStateRef.current.description === 'auto') {
      form.setValue('description', defaults.description, { shouldDirty: true });
    }
    if (autoStateRef.current.is_read_only === 'auto') {
      form.setValue('is_read_only', defaults.isReadOnly, { shouldDirty: true });
    }
    if (autoStateRef.current.required_permission === 'auto') {
      form.setValue('required_permission', defaults.requiredPermission, { shouldDirty: true });
    }
    if (autoStateRef.current.parameters === 'auto' && defaults.defaultParameters.length > 0) {
      form.setValue('parameters', defaults.defaultParameters, { shouldDirty: true });
    }
  }, [selectedType, selectedReferenceDoctype, mode, form, template.id]);

  // Auto-fill mandatory params for Create Document / Create Multiple Documents
  useEffect(() => {
    const shouldAutofill =
      selectedType === 'Create Document' || selectedType === 'Create Multiple Documents';
    if (!shouldAutofill || !selectedReferenceDoctype) return;
    // Don't fight the user once they've touched the parameter table manually.
    if (autoStateRef.current.parameters === 'edited') return;

    const autofillMandatoryFields = async () => {
      try {
        const meta = await getDocTypeMeta(selectedReferenceDoctype);
        const metaFields = Array.isArray(meta?.fields) ? meta.fields : [];
        const currentParams = (form.getValues('parameters') || []) as ParameterData[];
        const mandatoryRows = buildMissingMandatoryParameters(metaFields, currentParams);

        if (mandatoryRows.length > 0) {
          form.setValue('parameters', [...currentParams, ...mandatoryRows], {
            shouldDirty: true,
          });
        }
      } catch (error) {
        // Keep silent; user can still manually add params.
        console.error('Error auto-filling mandatory parameters:', error);
      }
    };

    autofillMandatoryFields();
  }, [selectedType, selectedReferenceDoctype, form]);

  const toolTypeOptions = toolTypes.map((type) => ({
    value: type.name,
    label: getToolTypeDisplayLabel(type.name1 || type.name),
  }));

  const operationTypeOptions = template.toolTypes;

  const handleSubmit = async (data: ToolFormData) => {
    await onSubmit(data);
  };

  // Handle child table operations
  const handleAddParameter = () => {
    markEdited('parameters');
    const current = form.getValues('parameters') || [];
    form.setValue('parameters', [
      ...current,
      {
        label: '',
        fieldname: '',
        type: 'string' as const,
        required: false,
        description: '',
        options: '',
        child_table_name: '',
      },
    ]);
  };

  const handleUpdateParameter = (index: number, data: Partial<ParameterData>) => {
    markEdited('parameters');
    const current = form.getValues('parameters') || [];
    const updated = [...current];
    updated[index] = { ...updated[index], ...data };
    form.setValue('parameters', updated);
  };

  const handleDeleteParameter = (index: number) => {
    markEdited('parameters');
    const current = form.getValues('parameters') || [];
    form.setValue('parameters', current.filter((_, i) => i !== index));
    if (editingParameterIndex !== null) {
      if (editingParameterIndex === index) {
        setEditingParameterIndex(null);
      } else if (editingParameterIndex > index) {
        setEditingParameterIndex(editingParameterIndex - 1);
      }
    }
  };

  const handleAddParametersFromDocType = (newRows: ParameterData[]) => {
    markEdited('parameters');
    const current = (form.getValues('parameters') || []) as ParameterData[];
    form.setValue('parameters', [...current, ...newRows], { shouldDirty: true });
    toast.success('Fields added');
  };

  const handleAddHttpHeader = () => {
    const current = form.getValues('http_headers') || [];
    form.setValue('http_headers', [...current, { key: '', value: '' }]);
  };

  const handleUpdateHttpHeader = (index: number, data: Partial<HttpHeaderData>) => {
    const current = form.getValues('http_headers') || [];
    const updated = [...current];
    updated[index] = { ...updated[index], ...data };
    form.setValue('http_headers', updated);
  };

  const handleDeleteHttpHeader = (index: number) => {
    const current = form.getValues('http_headers') || [];
    form.setValue('http_headers', current.filter((_, i) => i !== index));
  };

  const handleFetchParamsFromCode = async () => {
    const functionPath = (form.getValues('function_path') || '').trim();
    if (!functionPath) {
      toast.error('Please provide a Function Path first.');
      return;
    }

    setFetchingCodeParams(true);
    try {
      const response = await fetchToolParametersFromCode(functionPath);
      const fetchedParams = (response?.parameters || []).map((param) => ({
        label: param.label || param.fieldname,
        fieldname: param.fieldname,
        type: (param.type || 'string') as ParameterData['type'],
        required: param.required === 1 || param.required === true,
        description: '',
        options: '',
        child_table_name: '',
      }));

      form.setValue('parameters', fetchedParams, { shouldDirty: true });
      markEdited('parameters');
      form.setValue(
        'pass_parameters_as_json',
        response?.pass_parameters_as_json === 1 || response?.pass_parameters_as_json === true,
        { shouldDirty: true }
      );

      toast.success('Parameters updated from function signature.');
    } catch (error) {
      console.error('Error fetching parameters from code:', error);
    } finally {
      setFetchingCodeParams(false);
    }
  };

  const parameters = form.watch('parameters') || [];
  const httpHeaders = form.watch('http_headers') || [];
  const formToolName = form.watch('tool_name');
  const formToolType = form.watch('tool_type');
  const description = form.watch('description');
  const autoAddToAgent = form.watch('auto_add_to_agent');
  const requiredPermission = form.watch('required_permission');
  const isReadOnly = form.watch('is_read_only');
  const allowedForGuest = form.watch('allowed_for_guest');

  const [contractOpen, setContractOpen] = useState(false);
  const [guardrailsOpen, setGuardrailsOpen] = useState(false);

  // One-line summary shown on the collapsed "Details" section header.
  const contractSummary = useMemo(() => {
    const category = formToolType || 'No category';
    const desc = (description || '').trim();
    const truncated = desc.length > 60 ? `${desc.slice(0, 60)}…` : desc;
    return truncated ? `${category} · ${truncated}` : category;
  }, [formToolType, description]);

  // One-line summary shown on the collapsed "Guardrails" section header.
  const guardrailsSummary = useMemo(() => {
    const permission = requiredPermission
      ? requiredPermission.charAt(0).toUpperCase() + requiredPermission.slice(1)
      : 'Any permission';
    const mutability = isReadOnly ? 'Read-only' : 'Writable';
    const guests = allowedForGuest ? 'Guest access' : 'Not for guests';
    return `${permission} · ${mutability} · ${guests}`;
  }, [requiredPermission, isReadOnly, allowedForGuest]);

  const { parameterSchema, functionDefinition } = useMemo(() => {
    const properties: Record<string, Record<string, unknown>> = {};
    const required: string[] = [];

    parameters.forEach((param) => {
      if (!param.fieldname) return;
      const property: Record<string, unknown> = {
        type: param.type || 'string',
      };
      if (param.description) {
        property.description = param.description;
      }
      if (param.options?.trim()) {
        property.enum = parseParameterOptions(param.options);
      }
      properties[param.fieldname] = property;
      if (param.required) {
        required.push(param.fieldname);
      }
    });

    const schema: Record<string, unknown> = {
      type: 'object',
      properties,
    };
    if (required.length > 0) {
      schema.required = required;
    }

    const functionDef = buildFunctionDefinition({
      toolName: formToolName,
      description,
      types: selectedType,
      referenceDoctype: selectedReferenceDoctype,
      parameters,
    });

    return {
      parameterSchema: schema,
      functionDefinition: functionDef,
    };
  }, [parameters, formToolName, description, selectedType, selectedReferenceDoctype]);

  const showAutoBadges =
    mode === 'create' && isDocumentOperationType(selectedType) && !!selectedReferenceDoctype;

  const renderAutoBadge = (key: AutoFieldKey) => {
    // tool_type is auto-derived from the template for all five tool-type
    // bodies, so its badge does not depend on verb/DocType selection.
    const visible = key === 'tool_type' ? mode === 'create' : showAutoBadges;
    if (!visible) return null;
    return autoBadges[key] === 'auto' ? (
      <Badge variant="secondary" size="sm" className="ml-2 font-normal">
        Auto
      </Badge>
    ) : (
      <Badge variant="outline" size="sm" className="ml-2 font-normal">
        Edited
      </Badge>
    );
  };

  const parameterColumns = useMemo<ColumnDef<ParameterData>[]>(
    () => [
      {
        id: 'no',
        header: '#',
        cell: ({ row }) => (
          <span className="text-steel">{row.index + 1}</span>
        ),
      },
      {
        accessorKey: 'fieldname',
        header: 'Fieldname',
        cell: ({ row }) => (
          <span className="font-mono text-sm">{row.original.fieldname || '-'}</span>
        ),
      },
      {
        accessorKey: 'description',
        header: 'Description',
        cell: ({ row }) => (
          <span className="text-steel">{row.original.description || '-'}</span>
        ),
      },
      {
        accessorKey: 'type',
        header: 'Type',
        cell: ({ row }) => (
          <Badge variant="outline" size="sm">
            {row.original.type}
          </Badge>
        ),
      },
      {
        accessorKey: 'required',
        header: 'Req',
        cell: ({ row }) =>
          row.original.required ? <Check className="w-4 h-4 text-good" /> : '-',
      },
      {
        id: 'actions',
        header: () => <div className="text-right">Actions</div>,
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setEditingParameterIndex(row.index)}
              title="Edit parameter"
            >
              <Pencil className="w-4 h-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => handleDeleteParameter(row.index)}
              title="Delete parameter"
            >
              <Trash2 className="w-4 h-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  const parameterTable = useReactTable({
    data: parameters,
    columns: parameterColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  const renderParameterEditorView = () => {
    if (editingParameterIndex === null) return null;
    const parameter = parameters[editingParameterIndex];

    return (
      <div className="space-y-4 animate-in slide-in-from-right-4 fade-in duration-300">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setEditingParameterIndex(null)}
          className="shrink-0"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Tool Settings
        </Button>

        <div className="rounded border bg-paper px-3 py-2 text-sm font-medium">
          Edit Parameter {editingParameterIndex + 1}
        </div>

        {parameter ? (
          <ParameterCard
            parameter={parameter}
            index={editingParameterIndex}
            onChange={handleUpdateParameter}
            onDelete={(index) => {
              handleDeleteParameter(index);
              setEditingParameterIndex(null);
            }}
          />
        ) : (
          <div className="text-sm text-steel rounded border p-4">
            Parameter not found.
          </div>
        )}
      </div>
    );
  };

  const renderSettingsView = () => (
    <div className={editingParameterIndex === null ? 'animate-in fade-in duration-200' : ''}>
      {editingParameterIndex !== null ? renderParameterEditorView() : (
        <div className="space-y-8 pb-2">
      {/* CORE CONFIGURATION Section */}
      <div className="space-y-4 rounded-lg border border-line bg-panel p-4">
        <SectionHeader icon={Settings} title="Core configuration" />

        <FormField
          control={form.control}
          name="tool_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Tool Name<span className="text-destructive">*</span>
                {renderAutoBadge('tool_name')}
              </FormLabel>
              <FormControl>
                <Input
                  placeholder="e.g. create_sales_order"
                  className="bg-background"
                  {...field}
                  onChange={(e) => {
                    field.onChange(e);
                    markEdited('tool_name');
                  }}
                  disabled={loading}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

      </div>

      {/* OPERATION DETAILS Section */}
      <div className="space-y-4 rounded-lg border border-line bg-panel p-4">
        <SectionHeader icon={Zap} title="Operation details" />

        <FormField
          control={form.control}
          name="types"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Operation Type<span className="text-destructive">*</span>
              </FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
                disabled={loading}
              >
                <FormControl>
                  <SelectTrigger className="bg-background">
                    <SelectValue placeholder="Select Operation Type..." />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {operationTypeOptions.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Conditional Fields */}
        {selectedType && shouldShowField('reference_doctype', selectedType) && (
          <FormField
            control={form.control}
            name="reference_doctype"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Reference DocType<span className="text-destructive">*</span>
                </FormLabel>
                <FormControl>
                  <Combobox
                    options={docTypeOptions}
                    value={field.value}
                    onValueChange={field.onChange}
                    placeholder="Select DocType..."
                    searchPlaceholder="Search DocTypes..."
                    emptyText="No DocType found."
                    disabled={loading || loadingData}
                    className="bg-background"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {selectedType && shouldShowField('agent', selectedType) && (
          <FormField
            control={form.control}
            name="agent"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Select Agent<span className="text-destructive">*</span>
                </FormLabel>
                <FormControl>
                  <Combobox
                    options={agentOptions}
                    value={field.value}
                    onValueChange={field.onChange}
                    placeholder="Select Agent..."
                    searchPlaceholder="Search agents..."
                    emptyText="No agent found."
                    disabled={loading || loadingData}
                    linkTo={linkRoutes.agent}
                    className="bg-background"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {selectedType && shouldShowField('function_path', selectedType) && (
          <FormField
            control={form.control}
            name="function_path"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Function Path</FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g., my_app.api.my_function"
                    className="bg-background"
                    {...field}
                    disabled={loading}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {selectedType && shouldShowField('function_name', selectedType) && (
          <FormField
            control={form.control}
            name="function_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Function Name</FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g., myClientFunction"
                    className="bg-background"
                    {...field}
                    disabled={loading}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {selectedType && shouldShowField('provider_app', selectedType) && (
          <FormField
            control={form.control}
            name="provider_app"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Provider App</FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g., my_app"
                    className="bg-background"
                    {...field}
                    disabled={loading}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {selectedType && shouldShowField('base_url', selectedType) && (
          <FormField
            control={form.control}
            name="base_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Base URL</FormLabel>
                <FormControl>
                  <Input
                    placeholder="e.g., https://api.example.com"
                    className="bg-background"
                    {...field}
                    disabled={loading}
                  />
                </FormControl>
                <FormDescription>
                  Optional base URL that will be prefixed to the URL provided by the agent
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {selectedType && shouldShowField('pass_parameters_as_json', selectedType) && (
          <FormField
            control={form.control}
            name="pass_parameters_as_json"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-md border p-4">
                <div className="space-y-0.5">
                  <FormLabel>Pass parameters as JSON</FormLabel>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    disabled={loading}
                  />
                </FormControl>
              </FormItem>
            )}
          />
        )}
      </div>

      {/* HTTP Headers Section (for GET/POST) */}
      {selectedType && shouldShowField('http_headers', selectedType) && (
        <div className="space-y-4 rounded-lg border border-line bg-panel p-4">
          <div className="flex items-center justify-between">
            <SectionHeader title="HTTP Headers" />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddHttpHeader}
              disabled={loading}
            >
              <Plus className="w-4 h-4 mr-2" />
              Add header
            </Button>
          </div>
          {httpHeaders.length === 0 ? (
            <div className="text-sm font-body text-steel text-center py-4 border border-dashed rounded">
              No headers added. Click "Add Header" to add one.
            </div>
          ) : (
            <div className="space-y-3">
              {httpHeaders.map((header, index) => (
                <HttpHeaderCard
                  key={index}
                  header={header}
                  index={index}
                  onChange={handleUpdateHttpHeader}
                  onDelete={handleDeleteHttpHeader}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Parameters Section */}
      <div className="space-y-4 rounded-lg border border-line bg-panel p-4">
        <div className="flex items-center justify-between">
          <SectionHeader title={<>Parameters{renderAutoBadge('parameters')}</>} />
          <div className="flex items-center gap-2">
            {selectedReferenceDoctype && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowFieldSelector(true)}
                disabled={loading}
              >
                Select Fields from DocType
              </Button>
            )}
            {selectedType === 'Custom Function' && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleFetchParamsFromCode}
                disabled={loading || fetchingCodeParams || !functionPathValue?.trim()}
              >
                {fetchingCodeParams ? 'Fetching...' : 'Fetch Params from Code'}
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowParamsPreview((prev) => !prev)}
              disabled={loading}
            >
              <Braces className="w-4 h-4 mr-2" />
              {showParamsPreview ? 'Hide Preview' : 'Preview JSON'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                handleAddParameter();
                const nextIndex = parameters.length;
                setEditingParameterIndex(nextIndex);
              }}
              disabled={loading}
            >
              <Plus className="w-4 h-4 mr-2" />
              Add parameter
            </Button>
          </div>
        </div>

        {parameters.length === 0 ? (
          <div className="text-sm font-body text-steel text-center py-4 border border-dashed rounded">
            No parameters added. Click "Add Parameter" to add one.
          </div>
        ) : (
          <div className="rounded-lg border overflow-hidden">
            <Table>
              <TableHeader>
                {parameterTable.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {parameterTable.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {showParamsPreview && (
          <div className="rounded-lg border border-line bg-ink p-4">
            <p className="text-xs uppercase tracking-wide text-steel-soft mb-2 font-mono">Parameters JSON schema preview</p>
            <pre className="text-xs overflow-x-auto font-mono text-steel-soft">{JSON.stringify(parameterSchema, null, 2)}</pre>
          </div>
        )}
      </div>

        </div>
      )}
    </div>
  );

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-7 px-1">
        {selectedReferenceDoctype && (
          <SelectDocTypeFieldsDialog
            open={showFieldSelector}
            onOpenChange={setShowFieldSelector}
            doctypeName={selectedReferenceDoctype}
            currentParameters={parameters}
            onAddParameters={handleAddParametersFromDocType}
          />
        )}
        {editingParameterIndex === null && (
          <div className="sticky top-0 z-10 bg-background border-b border-line py-3 mb-4">
            <div className="flex items-center justify-between gap-4">
              <Button
                type="button"
                variant="outline"
                onClick={onBack}
                disabled={loading}
                className="shrink-0"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
            </div>
          </div>
        )}
        {editingParameterIndex === null && mode === 'edit' && sharedUsedBy.length > 0 && (
          <Alert className="border-line bg-paper-deep/50">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              This is a shared tool. Changes will affect other agents using it: {sharedUsedBy.join(', ')}.
            </AlertDescription>
          </Alert>
        )}

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]">
          <div className="min-w-0">{renderSettingsView()}</div>

          {/* Right rail: contract, guardrails, then the persistent live preview */}
          <aside className="min-w-0 self-start xl:sticky xl:top-16 space-y-3">
            {/* CONTRACT (Tool Category + Description, collapsed by default) */}
            <Collapsible open={contractOpen} onOpenChange={setContractOpen} className="space-y-3">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  className="group h-auto w-full items-center justify-start gap-2 rounded bg-panel px-3 py-2.5 text-left hover:bg-paper-deep"
                  disabled={loading}
                >
                  <FileText className="w-4 h-4 text-steel-soft shrink-0" />
                  <h3 className="font-mono text-eyebrow uppercase text-steel shrink-0">Details</h3>
                  {!contractOpen && (
                    <span className="text-sm text-steel truncate ml-1">— {contractSummary}</span>
                  )}
                  <ChevronDown className="w-4 h-4 ml-auto shrink-0 text-steel-soft transition-transform group-data-[state=open]:rotate-180" />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-4 rounded-lg border border-line bg-panel p-4">
                <FormField
                  control={form.control}
                  name="tool_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Tool Category<span className="text-destructive">*</span>
                        {renderAutoBadge('tool_type')}
                      </FormLabel>
                      <FormControl>
                        <Combobox
                          options={toolTypeOptions}
                          value={field.value}
                          onValueChange={(value) => {
                            field.onChange(value);
                            markEdited('tool_type');
                          }}
                          placeholder="Select Tool Category..."
                          searchPlaceholder="Search tool categories..."
                          emptyText="No tool category found."
                          disabled={loading}
                          className="bg-background"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Description
                        {renderAutoBadge('description')}
                      </FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Describe what this tool does. The AI uses this description to decide when to call it."
                          className="min-h-[100px] bg-background"
                          {...field}
                          onChange={(e) => {
                            field.onChange(e);
                            markEdited('description');
                          }}
                          disabled={loading}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CollapsibleContent>
            </Collapsible>

            {/* GUARDRAILS (permission + access switches, collapsed by default) */}
            <Collapsible open={guardrailsOpen} onOpenChange={setGuardrailsOpen} className="space-y-3">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  className="group h-auto w-full items-center justify-start gap-2 rounded bg-panel px-3 py-2.5 text-left hover:bg-paper-deep"
                  disabled={loading}
                >
                  <ShieldCheck className="w-4 h-4 text-steel-soft shrink-0" />
                  <h3 className="font-mono text-eyebrow uppercase text-steel shrink-0">Guardrails</h3>
                  {!guardrailsOpen && (
                    <span className="text-sm text-steel truncate ml-1">— {guardrailsSummary}</span>
                  )}
                  <ChevronDown className="w-4 h-4 ml-auto shrink-0 text-steel-soft transition-transform group-data-[state=open]:rotate-180" />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-4 rounded-lg border border-line bg-panel p-4">
                <FormField
                  control={form.control}
                  name="required_permission"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Required permission
                        {renderAutoBadge('required_permission')}
                      </FormLabel>
                      <Select
                        onValueChange={(value) => {
                          field.onChange(value);
                          markEdited('required_permission');
                        }}
                        value={field.value}
                        disabled={loading}
                      >
                        <FormControl>
                          <SelectTrigger className="bg-background">
                            <SelectValue placeholder="Select permission level..." />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="read">Read</SelectItem>
                          <SelectItem value="write">Write</SelectItem>
                          <SelectItem value="create">Create</SelectItem>
                          <SelectItem value="delete">Delete</SelectItem>
                          <SelectItem value="submit">Submit</SelectItem>
                          <SelectItem value="cancel">Cancel</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription>Permission level required to use this tool</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="is_read_only"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between rounded border p-4">
                      <div className="space-y-0.5">
                        <FormLabel>
                          Read only
                          {renderAutoBadge('is_read_only')}
                        </FormLabel>
                        <p className="text-sm text-steel">
                          If checked, this tool does not modify data
                        </p>
                      </div>
                      <FormControl>
                        <Switch
                          checked={field.value}
                          onCheckedChange={(checked) => {
                            field.onChange(checked);
                            markEdited('is_read_only');
                          }}
                          disabled={loading}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="allowed_for_guest"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between rounded border p-4">
                      <div className="space-y-0.5">
                        <FormLabel>Allowed for Guest</FormLabel>
                        <p className="text-sm text-steel">
                          If checked, Guest users can use this tool
                        </p>
                      </div>
                      <FormControl>
                        <Switch
                          checked={field.value}
                          onCheckedChange={field.onChange}
                          disabled={loading}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </CollapsibleContent>
            </Collapsible>

            <div className="flex items-center justify-between gap-2">
              <SectionHeader icon={Braces} title="Function Definition" />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowTestDrawer(true)}
                disabled={loading}
              >
                <FlaskConical className="w-4 h-4 mr-2" />
                Test call
              </Button>
            </div>
            <p className="text-xs text-steel">
              Live schema generated from your current settings — this is what the AI receives.
            </p>
            <div className="rounded-lg border border-line bg-ink p-4 max-h-[70vh] overflow-auto">
              <pre className="text-xs font-mono text-steel-soft whitespace-pre-wrap break-words">
                {JSON.stringify(functionDefinition, null, 2)}
              </pre>
            </div>
          </aside>
        </div>

        <TestToolDrawer
          open={showTestDrawer}
          onOpenChange={setShowTestDrawer}
          toolName={formToolName}
          types={selectedType}
          referenceDoctype={selectedReferenceDoctype}
          functionDefinition={functionDefinition}
        />

        {/* Footer */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-end gap-4 pt-4 border-t">
          {mode === 'create' && (
            <FormField
              control={form.control}
              name="auto_add_to_agent"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center gap-2 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      disabled={loading}
                    />
                  </FormControl>
                  <FormLabel className="font-normal text-sm cursor-pointer">
                    Auto-add tool to this agent
                  </FormLabel>
                </FormItem>
              )}
            />
          )}
          <Button
            type="submit"
            disabled={loading}
          >
            {loading
              ? (mode === 'edit' ? 'Updating...' : 'Creating...')
              : (mode === 'edit'
                  ? 'Update Tool'
                  : (autoAddToAgent ? 'Create & Add Tool' : 'Create Tool'))
            }
          </Button>
        </div>
      </form>
    </Form>
  );
}
