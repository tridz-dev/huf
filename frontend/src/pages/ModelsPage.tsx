import { Cpu, Settings, Loader2, DollarSign } from 'lucide-react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
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
import { PageLayout, FilterBar, GridView, LoadMoreButton } from '../components/dashboard';
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
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import type { AIModel, AIProvider } from '../types/agent.types';

interface ModelsPageProps {
  addModelKey?: number;
}

interface ModelFormData {
  model_name: string;
  provider: string;
  modalities: string;
  use_custom_pricing: boolean;
  input_cost_per_1m_tokens: string;
  output_cost_per_1m_tokens: string;
  cached_input_cost_per_1m_tokens: string;
}

const emptyFormData: ModelFormData = {
  model_name: '',
  provider: '',
  modalities: '',
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
        modalities: details.modalities || '',
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

  const buildModelPayload = () => {
    const payload: Record<string, unknown> = {
      model_name: formData.model_name.trim(),
      provider: formData.provider,
      modalities: formData.modalities,
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

  return (
    <PageLayout
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
          <p className="text-sm text-muted-foreground mb-4">{error.message || 'An error occurred while fetching models.'}</p>
        </div>
      )}
      <GridView
        items={models}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No models found.</p>
          </div>
        }
        renderItem={(model) => {
          const pricingSummary = formatPricingSummary(model);

          return (
            <Card key={model.name} className="h-full flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Cpu className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{model.model_name}</CardTitle>
                      <CardDescription className="text-xs">
                        {resolveProviderName(model.provider, providerMap)}
                      </CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1 space-y-2">
                <div className="flex flex-wrap gap-2">
                  {parseModalityBadges(model.modalities).map((modality) => (
                    <Badge key={modality} variant="secondary" className="text-xs">
                      {modality}
                    </Badge>
                  ))}
                </div>
                {model.use_custom_pricing === 1 && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <DollarSign className="w-3 h-3" />
                    <span>{pricingSummary || 'Custom pricing'}</span>
                  </div>
                )}
              </CardContent>
              <CardFooter>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 gap-2"
                  onClick={() => handleConfigure(model)}
                >
                  <Settings className="w-4 h-4" />
                  Configure
                </Button>
              </CardFooter>
            </Card>
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
        <div className="text-center py-4 text-sm text-muted-foreground">
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
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
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
              </div>

              <div className="space-y-2">
                <Label htmlFor="modalities">Modality</Label>
                <Select
                  value={formData.modalities}
                  onValueChange={(value) => setFormData({ ...formData, modalities: value })}
                >
                  <SelectTrigger id="modalities">
                    <SelectValue placeholder="Select a modality" />
                  </SelectTrigger>
                  <SelectContent>
                    {modalityOptions.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="border-t pt-4 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="use_custom_pricing">Enable Custom Pricing</Label>
                    <p className="text-xs text-muted-foreground">
                      Override LiteLLM automatic pricing (USD per 1M tokens)
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
    </PageLayout>
  );
}
