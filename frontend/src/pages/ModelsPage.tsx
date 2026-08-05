import { Cpu, Settings, Loader2, DollarSign } from 'lucide-react';
import { Button } from '../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, ItemCard, LoadMoreButton, EmptyState } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import {
  getModels,
  getModel,
  updateModel,
  createModel,
  getProviders,
  getModalityOptions,
  buildProviderNameMap,
  resolveProviderName,
} from '../services/providerApi';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import type { AIModel, AIProvider } from '../types/agent.types';
import { LinkFieldControl } from '../components/ui/link-field-control';
import { MultiSelectCombobox } from '../components/ui/multi-select-combobox';
import { linkRoutes } from '../lib/link-routes';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

interface ModelsPageProps {
  addModelKey?: number;
}

interface ModelFormData {
  model_name: string;
  provider: string;
  modalities: string[];
  use_custom_pricing: boolean;
  input_cost_per_1m_tokens: string;
  output_cost_per_1m_tokens: string;
  cached_input_cost_per_1m_tokens: string;
}

const emptyFormData: ModelFormData = {
  model_name: '',
  provider: '',
  modalities: [],
  use_custom_pricing: false,
  input_cost_per_1m_tokens: '',
  output_cost_per_1m_tokens: '',
  cached_input_cost_per_1m_tokens: '',
};

function parseModalityBadges(modalities?: string): string[] {
  if (!modalities?.trim()) return ['Text'];
  return modalities.split(',').map((m) => m.trim()).filter(Boolean);
}

function formatPricingSummary(model: AIModel): string | null {
  if (model.use_custom_pricing !== 1) return null;
  const input = model.input_cost_per_1m_tokens;
  const output = model.output_cost_per_1m_tokens;
  if (input == null && output == null) return 'Custom pricing';
  const parts: string[] = [];
  if (input != null) parts.push(`In $${input}/1M`);
  if (output != null) parts.push(`Out $${output}/1M`);
  return parts.join(' · ');
}

export function ModelsPage({ addModelKey }: ModelsPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const configureHandledRef = useRef(false);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [modalityOptions, setModalityOptions] = useState<string[]>([]);
  const [configureModalOpen, setConfigureModalOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<AIModel | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingModel, setLoadingModel] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState<ModelFormData>(emptyFormData);

  const providerMap = useMemo(() => buildProviderNameMap(providers), [providers]);

  const {
    items: models,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    reset,
    error,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    AIModel
  >({
    fetchFn: async (params) => {
      const response = await getModels({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: {},
    pageSize: 10,
    debounceMs: 300,
    autoLoad: true,
  });

  useEffect(() => {
    getProviders().then((data) => {
      if (Array.isArray(data)) {
        setProviders(data);
      } else {
        setProviders(data.items);
      }
    }).catch((fetchError) => {
      console.error('Error fetching providers:', fetchError);
    });

    getModalityOptions().then((options) => {
      setModalityOptions(options);
    }).catch((fetchError) => {
      console.error('Error fetching modality options:', fetchError);
    });
  }, []);

  useEffect(() => {
    if (error) {
      toast.error('Failed to load models', {
        description: error.message || 'An error occurred while fetching models. Please try again.',
        duration: 5000,
      });
    }
  }, [error]);

  const handleAddModel = () => {
    setSelectedModel(null);
    setIsEditing(false);
    setFormData(emptyFormData);
    setConfigureModalOpen(true);
  };

  useEffect(() => {
    if (addModelKey && addModelKey > 0) {
      handleAddModel();
    }
  }, [addModelKey]);

  const handleConfigure = async (model: AIModel) => {
    setSelectedModel(model);
    setIsEditing(true);
    setConfigureModalOpen(true);
    setLoadingModel(true);

    try {
      const details = await getModel(model.name);
      setFormData({
        model_name: details.model_name || '',
        provider: details.provider || '',
        modalities: details.modalities
          ? details.modalities.split(',').map((m) => m.trim()).filter(Boolean)
          : [],
        use_custom_pricing: details.use_custom_pricing === 1,
        input_cost_per_1m_tokens:
          details.input_cost_per_1m_tokens != null ? String(details.input_cost_per_1m_tokens) : '',
        output_cost_per_1m_tokens:
          details.output_cost_per_1m_tokens != null ? String(details.output_cost_per_1m_tokens) : '',
        cached_input_cost_per_1m_tokens:
          details.cached_input_cost_per_1m_tokens != null
            ? String(details.cached_input_cost_per_1m_tokens)
            : '',
      });
    } catch (loadError) {
      toast.error('Failed to load model details');
      console.error(loadError);
    } finally {
      setLoadingModel(false);
    }
  };

  useEffect(() => {
    const configureId = searchParams.get('configure');
    if (!configureId || configureHandledRef.current) {
      return;
    }

    configureHandledRef.current = true;
    let cancelled = false;

    const openFromDeepLink = async () => {
      try {
        const listMatch = models.find((model) => model.name === configureId);
        if (listMatch) {
          await handleConfigure(listMatch);
        } else {
          const details = await getModel(configureId);
          await handleConfigure(details);
        }
      } catch (loadError) {
        if (!cancelled) {
          toast.error('Failed to open model configuration');
          console.error(loadError);
        }
      } finally {
        if (!cancelled) {
          setSearchParams({}, { replace: true });
        }
      }
    };

    openFromDeepLink();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const buildModelPayload = () => {
    const payload: Record<string, unknown> = {
      model_name: formData.model_name.trim(),
      provider: formData.provider,
      modalities: formData.modalities.join(','),
      use_custom_pricing: formData.use_custom_pricing ? 1 : 0,
    };

    if (formData.use_custom_pricing) {
      payload.input_cost_per_1m_tokens = formData.input_cost_per_1m_tokens
        ? parseFloat(formData.input_cost_per_1m_tokens)
        : 0;
      payload.output_cost_per_1m_tokens = formData.output_cost_per_1m_tokens
        ? parseFloat(formData.output_cost_per_1m_tokens)
        : 0;
      payload.cached_input_cost_per_1m_tokens = formData.cached_input_cost_per_1m_tokens
        ? parseFloat(formData.cached_input_cost_per_1m_tokens)
        : 0;
    }

    return payload;
  };

  const handleSave = async () => {
    if (!formData.model_name.trim()) {
      toast.error('Model name is required');
      return;
    }
    if (!formData.provider) {
      toast.error('Provider is required');
      return;
    }

    setSaving(true);
    try {
      const payload = buildModelPayload();
      if (isEditing && selectedModel) {
        await updateModel(selectedModel.name, payload);
        toast.success('Model updated successfully');
      } else {
        await createModel(payload);
        toast.success('Model created successfully');
      }
      setConfigureModalOpen(false);
      reset();
    } catch (saveError) {
      toast.error(`Failed to ${isEditing ? 'update' : 'create'} model`);
      console.error(saveError);
    } finally {
      setSaving(false);
    }
  };

  useSaveShortcut({
    onSave: handleSave,
    enabled: configureModalOpen && !loadingModel,
    isSubmitting: saving,
    allowInDialog: true,
  });

  return (
    <PageFrame
      title="Models"
      subtitle="Manage AI models and their capabilities"
      filters={
        <FilterBar
          searchPlaceholder="Search models..."
          searchValue={search}
          onSearchChange={setSearch}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load models</p>
          <p className="text-sm text-steel mb-4">{error.message || 'An error occurred while fetching models.'}</p>
        </div>
      )}
      <GridView
        items={models}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <EmptyState
            icon={Cpu}
            title="No models"
            description="Add a model to use with your AI providers."
            action={{ label: 'Add model', onClick: handleAddModel }}
          />
        }
        renderItem={(model) => {
          const pricingSummary = formatPricingSummary(model);
          const modalities = parseModalityBadges(model.modalities);

          return (
            <ItemCard
              key={model.name}
              title={model.model_name}
              description={resolveProviderName(model.provider, providerMap)}
              icon={Cpu}
              metadata={[
                { label: 'Provider', value: resolveProviderName(model.provider, providerMap), icon: undefined },
                ...(pricingSummary ? [{ label: 'Pricing', value: pricingSummary, icon: DollarSign }] : []),
              ]}
              badges={modalities.map((modality) => ({
                label: modality,
                variant: 'secondary' as const,
              }))}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () => handleConfigure(model),
                  variant: 'ghost',
                },
              ]}
              onClick={() => handleConfigure(model)}
            />
          );
        }}
        keyExtractor={(model) => model.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && models.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} models` : 'No more models to load'}
        </div>
      )}

      <Dialog open={configureModalOpen} onOpenChange={setConfigureModalOpen}>
        <DialogContent className="sm:max-w-[520px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {isEditing ? `Configure ${selectedModel?.model_name || 'Model'}` : 'Add Model'}
            </DialogTitle>
            <DialogDescription>
              {isEditing ? 'Update model configuration settings' : 'Create a new AI model'}
            </DialogDescription>
          </DialogHeader>

          {loadingModel ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
            </div>
          ) : (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="model_name">
                  Model Name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="model_name"
                  type="text"
                  placeholder="Enter model name (e.g., gpt-4, claude-3)"
                  value={formData.model_name}
                  onChange={(e) => setFormData({ ...formData, model_name: e.target.value })}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="provider">
                  Provider <span className="text-destructive">*</span>
                </Label>
                <LinkFieldControl
                  value={formData.provider}
                  linkTo={linkRoutes.aiProvider}
                >
                  <Select
                    value={formData.provider}
                    onValueChange={(value) => setFormData({ ...formData, provider: value })}
                  >
                    <SelectTrigger id="provider">
                      <SelectValue placeholder="Select a provider" />
                    </SelectTrigger>
                    <SelectContent>
                      {providers.map((p) => (
                        <SelectItem key={p.name} value={p.name}>
                          {p.provider_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </LinkFieldControl>
              </div>

              <div className="space-y-2">
                <Label htmlFor="modalities">Modality</Label>
                <MultiSelectCombobox
                  options={modalityOptions.map((opt) => ({ value: opt, label: opt }))}
                  values={formData.modalities}
                  onValuesChange={(values) => setFormData({ ...formData, modalities: values })}
                  placeholder="Select modalities"
                  searchPlaceholder="Search modalities..."
                />
                <p className="text-xs text-steel-soft">
                  Select one or more supported modalities / tasks for this model. Used to filter model pickers (e.g. image generation, TTS, transcription).
                </p>
              </div>

              <div className="border-t pt-4 space-y-4">
                <p className="text-xs text-steel-soft">
                  Enable custom prices to override LiteLLM&apos;s automatic pricing lookup. When disabled, LiteLLM&apos;s built-in price table is used as fallback. Values are in USD per 1 million tokens.
                </p>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="use_custom_pricing">Enable custom pricing</Label>
                    <p className="text-xs text-steel-soft">
                      Check this to activate the custom prices below. When unchecked, LiteLLM&apos;s automatic pricing is used regardless of what is entered below.
                    </p>
                  </div>
                  <Switch
                    id="use_custom_pricing"
                    checked={formData.use_custom_pricing}
                    onCheckedChange={(checked) =>
                      setFormData({ ...formData, use_custom_pricing: checked })
                    }
                  />
                </div>

                {formData.use_custom_pricing && (
                  <div className="space-y-3">
                    <div className="space-y-2">
                      <Label htmlFor="input_cost">Input Cost per 1M Tokens (USD)</Label>
                      <p className="text-xs text-steel-soft">
                        Cost in USD per 1 million prompt/input tokens. E.g. enter 2.50 for $2.50 per 1M tokens. Enter 0 for free/self-hosted models.
                      </p>
                      <Input
                        id="input_cost"
                        type="number"
                        min="0"
                        step="0.00000001"
                        placeholder="e.g. 2.50"
                        value={formData.input_cost_per_1m_tokens}
                        onChange={(e) =>
                          setFormData({ ...formData, input_cost_per_1m_tokens: e.target.value })
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="output_cost">Output Cost per 1M Tokens (USD)</Label>
                      <p className="text-xs text-steel-soft">
                        Cost in USD per 1 million completion/output tokens. E.g. enter 10.00 for $10.00 per 1M tokens.
                      </p>
                      <Input
                        id="output_cost"
                        type="number"
                        min="0"
                        step="0.00000001"
                        placeholder="e.g. 10.00"
                        value={formData.output_cost_per_1m_tokens}
                        onChange={(e) =>
                          setFormData({ ...formData, output_cost_per_1m_tokens: e.target.value })
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="cached_input_cost">Cached Input Cost per 1M Tokens (USD)</Label>
                      <p className="text-xs text-steel-soft">
                        Optional. Cost for prompt cache reads (cache hits) in USD per 1M tokens. E.g. Anthropic charges $0.30/1M for cache reads vs $3.00/1M for regular input. Leave as 0 if not applicable.
                      </p>
                      <Input
                        id="cached_input_cost"
                        type="number"
                        min="0"
                        step="0.00000001"
                        placeholder="Optional, e.g. 0.30"
                        value={formData.cached_input_cost_per_1m_tokens}
                        onChange={(e) =>
                          setFormData({ ...formData, cached_input_cost_per_1m_tokens: e.target.value })
                        }
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfigureModalOpen(false)}
              disabled={saving || loadingModel}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || loadingModel}
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {isEditing ? 'Saving...' : 'Creating...'}
                </>
              ) : (
                isEditing ? 'Save' : 'Create'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageFrame>
  );
}
