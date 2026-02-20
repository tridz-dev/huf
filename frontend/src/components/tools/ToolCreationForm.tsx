import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowLeft, Settings, Zap, Plus, Braces, Pencil, Trash2, Check, AlertTriangle } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Combobox } from '@/components/ui/combobox';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
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
import type { ToolTemplate, ToolFormData } from '@/types/toolTemplate.types';
import type { AgentToolType, ToolType } from '@/types/agent.types';
import { getDocTypeMeta } from '@/services/agentApi';
import { fetchToolParametersFromCode } from '@/services/toolApi';
import { toast } from 'sonner';
import { useToolCreationOptions } from './useToolCreationOptions';
import {
  buildMissingMandatoryParameters,
  createToolFormSchema,
  getDefaultToolFormValues,
  shouldShowField,
} from './toolCreationForm.utils';

interface ToolCreationFormProps {
  template: ToolTemplate;
  toolTypes: AgentToolType[];
  onSubmit: (data: ToolFormData) => Promise<void>;
  onBack: () => void;
  loading?: boolean;
  initialData?: Partial<ToolFormData> | null;
  mode?: 'create' | 'edit';
}

export function ToolCreationForm({
  template,
  toolTypes,
  onSubmit,
  onBack,
  loading = false,
  initialData = null,
  mode = 'create',
}: ToolCreationFormProps) {
  const formSchema = useMemo(() => createToolFormSchema(template.toolTypes), [template.toolTypes]);
  const { loadingData, docTypeOptions, agentOptions } = useToolCreationOptions();
  const [fetchingCodeParams, setFetchingCodeParams] = useState(false);
  const [configView, setConfigView] = useState<'settings' | 'function_definition'>('settings');
  const [editingParameterIndex, setEditingParameterIndex] = useState<number | null>(null);
  const [showParamsPreview, setShowParamsPreview] = useState(false);

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

  useEffect(() => {
    if (!loading) {
      setConfigView('settings');
      setEditingParameterIndex(null);
      setShowParamsPreview(false);
    }
  }, [loading]);

  // Watch the types field to conditionally show fields
  const selectedType = useWatch({ control: form.control, name: 'types' });
  const selectedReferenceDoctype = useWatch({ control: form.control, name: 'reference_doctype' });
  const functionPathValue = useWatch({ control: form.control, name: 'function_path' });

  // Auto-fill mandatory params for Create Document / Create Multiple Documents
  useEffect(() => {
    const shouldAutofill =
      selectedType === 'Create Document' || selectedType === 'Create Multiple Documents';
    if (!shouldAutofill || !selectedReferenceDoctype) return;

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
    label: type.name1 || type.name,
  }));

  const operationTypeOptions = template.toolTypes;

  const handleSubmit = async (data: ToolFormData) => {
    await onSubmit(data);
  };

  // Handle child table operations
  const handleAddParameter = () => {
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
    const current = form.getValues('parameters') || [];
    const updated = [...current];
    updated[index] = { ...updated[index], ...data };
    form.setValue('parameters', updated);
  };

  const handleDeleteParameter = (index: number) => {
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
  const toolName = form.watch('tool_name');
  const description = form.watch('description');
  const sharedUsedBy = initialData?.usedBy || [];

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
        property.enum = param.options.split(',').map((item) => item.trim()).filter(Boolean);
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

    const functionDef: Record<string, unknown> = {
      name: toolName || 'untitled_tool',
      description: description || 'No description provided.',
    };
    if (Object.keys(properties).length > 0) {
      functionDef.parameters = schema;
    }

    return {
      parameterSchema: schema,
      functionDefinition: functionDef,
    };
  }, [parameters, toolName, description]);

  const parameterColumns = useMemo<ColumnDef<ParameterData>[]>(
    () => [
      {
        id: 'no',
        header: '#',
        cell: ({ row }) => (
          <span className="text-muted-foreground">{row.index + 1}</span>
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
          <span className="text-muted-foreground">{row.original.description || '-'}</span>
        ),
      },
      {
        accessorKey: 'type',
        header: 'Type',
        cell: ({ row }) => (
          <Badge variant="outline" className="text-[10px]">
            {row.original.type}
          </Badge>
        ),
      },
      {
        accessorKey: 'required',
        header: 'Req',
        cell: ({ row }) =>
          row.original.required ? <Check className="w-4 h-4 text-green-600" /> : '-',
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
              <Trash2 className="w-4 h-4 text-red-600" />
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
          className="bg-white"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Tool Settings
        </Button>

        <div className="rounded-md border bg-background px-3 py-2 text-sm font-medium">
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
          <div className="text-sm text-muted-foreground rounded-md border p-4">
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
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-3">
          <Settings className="w-5 h-5 text-gray-600" />
          <h3 className="font-semibold text-gray-900">CORE CONFIGURATION</h3>
        </div>

        <FormField
          control={form.control}
          name="tool_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Tool Name<span className="text-red-500">*</span>
              </FormLabel>
              <FormControl>
                <Input
                  placeholder="e.g. create_sales_order"
                  {...field}
                  disabled={loading}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="tool_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Tool Category<span className="text-red-500">*</span>
              </FormLabel>
              <FormControl>
                <Combobox
                  options={toolTypeOptions}
                  value={field.value}
                  onValueChange={field.onChange}
                  placeholder="Select Tool Category..."
                  searchPlaceholder="Search tool categories..."
                  emptyText="No tool category found."
                  disabled={loading}
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
                Description<span className="text-red-500">*</span>
              </FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Describe what this tool does. The AI uses this description to decide when to call it."
                  className="min-h-[100px]"
                  {...field}
                  disabled={loading}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {/* OPERATION DETAILS Section */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-5 h-5 text-gray-600" />
          <h3 className="font-semibold text-gray-900">OPERATION DETAILS</h3>
        </div>

        <FormField
          control={form.control}
          name="types"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Operation Type<span className="text-red-500">*</span>
              </FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
                disabled={loading}
              >
                <FormControl>
                  <SelectTrigger>
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
                  Reference DocType<span className="text-red-500">*</span>
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
                  Select Agent<span className="text-red-500">*</span>
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
                    {...field}
                    disabled={loading}
                  />
                </FormControl>
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
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
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
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">HTTP Headers</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddHttpHeader}
              disabled={loading}
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Header
            </Button>
          </div>
          {httpHeaders.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-4 border border-dashed rounded-lg">
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
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Parameters</h3>
          <div className="flex items-center gap-2">
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
              Add Parameter
            </Button>
          </div>
        </div>

        {parameters.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-4 border border-dashed rounded-lg">
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
          <div className="rounded-lg border bg-black text-green-400 p-4">
            <p className="text-xs uppercase tracking-wide text-green-300 mb-2">Parameters JSON Schema Preview</p>
            <pre className="text-xs overflow-x-auto">{JSON.stringify(parameterSchema, null, 2)}</pre>
          </div>
        )}
      </div>

      {/* Optional Fields Section */}
      <div className="space-y-4 pt-1">
        <h3 className="font-semibold text-gray-900">Additional Settings</h3>

        <FormField
          control={form.control}
          name="required_permission"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Required Permission</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
                disabled={loading}
              >
                <FormControl>
                  <SelectTrigger>
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
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="is_read_only"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
              <div className="space-y-0.5">
                <FormLabel>Read Only</FormLabel>
                <p className="text-sm text-muted-foreground">
                  If checked, this tool does not modify data
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

        <FormField
          control={form.control}
          name="allowed_for_guest"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
              <div className="space-y-0.5">
                <FormLabel>Allowed for Guest</FormLabel>
                <p className="text-sm text-muted-foreground">
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
      </div>
        </div>
      )}
    </div>
  );

  const renderFunctionDefinitionView = () => (
    <div className="space-y-4">
      <div className="rounded-lg border bg-blue-50 p-4 text-sm text-blue-900 flex items-start gap-2">
        <Braces className="w-4 h-4 mt-0.5" />
        <div>
          <p className="font-medium">Function Definition Preview</p>
          <p className="text-blue-800">
            This JSON is generated from your current tool settings and parameter definitions.
          </p>
        </div>
      </div>
      <div className="rounded-lg border bg-black text-blue-300 p-4">
        <pre className="text-xs overflow-x-auto">{JSON.stringify(functionDefinition, null, 2)}</pre>
      </div>
    </div>
  );

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-7 px-1">
        {editingParameterIndex === null && (
          <div className="flex items-center justify-start">
            <Button
              type="button"
              variant="outline"
              onClick={onBack}
              disabled={loading}
              className="bg-white"
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
          </div>
        )}
        {editingParameterIndex === null && mode === 'edit' && sharedUsedBy.length > 0 && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 text-amber-700" />
            <p>
              This is a shared tool. Changes may affect other agents using it: {sharedUsedBy.join(', ')}.
            </p>
          </div>
        )}

        {editingParameterIndex === null && (
          <div className="flex items-center justify-between border-b pb-3">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-gray-900">{mode === 'edit' ? 'Edit Tool' : 'Configure Tool'}</h3>
              <Badge variant="outline">{template.name}</Badge>
            </div>
            <div className="flex items-center gap-1 rounded-md border p-1">
              <Button
                type="button"
                variant={configView === 'settings' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setConfigView('settings')}
              >
                <Settings className="w-4 h-4 mr-1" />
                Settings
              </Button>
              <Button
                type="button"
                variant={configView === 'function_definition' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setConfigView('function_definition')}
              >
                <Braces className="w-4 h-4 mr-1" />
                Function Def
              </Button>
            </div>
          </div>
        )}

        {configView === 'settings' ? renderSettingsView() : renderFunctionDefinitionView()}

        {/* Footer */}
        <div className="flex items-center justify-end pt-4 border-t">
          <Button
            type="submit"
            disabled={loading}
            className="bg-purple-600 hover:bg-purple-700 text-white"
          >
            {loading 
              ? (mode === 'edit' ? 'Updating...' : 'Creating...') 
              : (mode === 'edit' ? 'Update Tool' : 'Create & Add Tool')
            }
          </Button>
        </div>
      </form>
    </Form>
  );
}
