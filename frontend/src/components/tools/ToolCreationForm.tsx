import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Settings, Zap, Plus } from 'lucide-react';
import { useState, useEffect, useMemo } from 'react';
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
import { ParameterCard, type ParameterData } from './ParameterCard';
import { HttpHeaderCard, type HttpHeaderData } from './HttpHeaderCard';
import type { ToolTemplate, ToolFormData } from '@/types/toolTemplate.types';
import type { AgentToolType, ToolType } from '@/types/agent.types';
import { getDocTypes } from '@/services/agentApi';
import { getAgents } from '@/services/agentApi';
import type { AgentDoc } from '@/types/agent.types';

interface ToolCreationFormProps {
  template: ToolTemplate;
  toolTypes: AgentToolType[];
  onSubmit: (data: ToolFormData) => Promise<void>;
  onBack: () => void;
  loading?: boolean;
}

const createFormSchema = (availableToolTypes: ToolType[]) => {
  const toolTypesEnum = z.enum(availableToolTypes as [ToolType, ...ToolType[]]);
  
  return z.object({
    tool_name: z.string().min(1, 'Tool name is required').max(128, 'Tool name must be at most 128 characters'),
    tool_type: z.string().min(1, 'Tool category is required'),
    types: toolTypesEnum,
    description: z.string().min(1, 'Description is required'),
    // Conditional fields
    reference_doctype: z.string().optional(),
    agent: z.string().optional(),
    function_path: z.string().optional(),
    function_name: z.string().optional(),
    pass_parameters_as_json: z.boolean().optional(),
    provider_app: z.string().optional(),
    base_url: z.string().optional(),
    // Optional fields
    required_permission: z.enum(['read', 'write', 'create', 'delete', 'submit', 'cancel']).optional(),
    is_read_only: z.boolean().optional(),
    allowed_for_guest: z.boolean().optional(),
    // Child tables
    parameters: z.array(z.any()).optional(),
    http_headers: z.array(z.any()).optional(),
  });
};

// Helper to determine if field should be shown based on types
const shouldShowField = (fieldName: string, types: ToolType): boolean => {
  switch (fieldName) {
    case 'reference_doctype':
      return !['Run Agent', 'App Provided', 'Custom Function', 'Client Side Tool', 
               'Get Conversation Data', 'Set Conversation Data', 'Load Conversation Data'].includes(types);
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

export function ToolCreationForm({
  template,
  toolTypes,
  onSubmit,
  onBack,
  loading = false,
}: ToolCreationFormProps) {
  const formSchema = useMemo(() => createFormSchema(template.toolTypes), [template.toolTypes]);
  const [docTypes, setDocTypes] = useState<Array<{ name: string }>>([]);
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [loadingData, setLoadingData] = useState(false);

  const form = useForm<ToolFormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      tool_name: '',
      tool_type: '',
      types: template.toolTypes[0] as ToolType,
      description: '',
      parameters: [],
      http_headers: [],
      is_read_only: false,
      allowed_for_guest: false,
      pass_parameters_as_json: false,
    },
  });

  // Watch the types field to conditionally show fields
  const selectedType = useWatch({ control: form.control, name: 'types' });

  // Load DocTypes and Agents when form mounts
  useEffect(() => {
    const loadData = async () => {
      setLoadingData(true);
      try {
        const [doctypes, agentsList] = await Promise.all([
          getDocTypes(),
          getAgents(),
        ]);
        setDocTypes(doctypes || []);
        setAgents(Array.isArray(agentsList) ? agentsList : (agentsList as any)?.items || []);
      } catch (error) {
        console.error('Error loading data:', error);
      } finally {
        setLoadingData(false);
      }
    };
    loadData();
  }, []);

  const toolTypeOptions = toolTypes.map((type) => ({
    value: type.name,
    label: type.name1 || type.name,
  }));

  const operationTypeOptions = template.toolTypes;

  const docTypeOptions = docTypes.map((dt) => ({
    value: dt.name,
    label: dt.name,
  }));

  const agentOptions = agents.map((agent) => ({
    value: agent.name,
    label: agent.agent_name || agent.name,
  }));

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

  const parameters = form.watch('parameters') || [];
  const httpHeaders = form.watch('http_headers') || [];

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
        {/* CORE CONFIGURATION Section */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-4">
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
          <div className="flex items-center gap-2 mb-4">
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
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddParameter}
              disabled={loading}
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Parameter
            </Button>
          </div>
          {parameters.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-4 border border-dashed rounded-lg">
              No parameters added. Click "Add Parameter" to add one.
            </div>
          ) : (
            <div className="space-y-3">
              {parameters.map((param, index) => (
                <ParameterCard
                  key={index}
                  parameter={param}
                  index={index}
                  onChange={handleUpdateParameter}
                  onDelete={handleDeleteParameter}
                />
              ))}
            </div>
          )}
        </div>

        {/* Optional Fields Section */}
        <div className="space-y-4">
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

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t">
          <Button
            type="button"
            variant="ghost"
            onClick={onBack}
            disabled={loading}
            className="text-gray-600 hover:text-gray-900"
          >
            Back
          </Button>
          <Button
            type="submit"
            disabled={loading}
            className="bg-purple-600 hover:bg-purple-700 text-white"
          >
            {loading ? 'Creating...' : 'Create & Add Tool'}
          </Button>
        </div>
      </form>
    </Form>
  );
}
