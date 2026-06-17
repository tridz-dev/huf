import { Cpu, Settings, Loader2, Plus } from 'lucide-react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { FilterBar, GridView, LoadMoreButton } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getModels, getModel, updateModel, createModel, getProviders, getModalityOptions } from '../services/providerApi';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import type { AIModel, AIProvider } from '../types/agent.types';

interface ModelsPageProps {
  addModelKey?: number;
}

export function ModelsPage({ addModelKey }: ModelsPageProps) {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [modalityOptions, setModalityOptions] = useState<string[]>([]);
  const [configureModalOpen, setConfigureModalOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<AIModel | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingModel, setLoadingModel] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    model_name: '',
    provider: '',
    modalities: '',
  });

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

  // Fetch providers and modality options
  useEffect(() => {
    getProviders().then((data) => {
      if (Array.isArray(data)) {
        setProviders(data);
      } else {
        setProviders(data.items);
      }
    }).catch((error) => {
      console.error('Error fetching providers:', error);
    });

    getModalityOptions().then((options) => {
      setModalityOptions(options);
    }).catch((error) => {
      console.error('Error fetching modality options:', error);
    });
  }, []);

  // Show error toast when there's an error
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
    setFormData({
      model_name: '',
      provider: '',
      modalities: '',
    });
    setConfigureModalOpen(true);
  };

  // Listen for add model trigger from header
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
      });
    } catch (error) {
      toast.error('Failed to load model details');
      console.error(error);
    } finally {
      setLoadingModel(false);
    }
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
      if (isEditing && selectedModel) {
        await updateModel(selectedModel.name, {
          model_name: formData.model_name.trim(),
          provider: formData.provider,
          modalities: formData.modalities,
        });
        toast.success('Model updated successfully');
      } else {
        await createModel({
          model_name: formData.model_name.trim(),
          provider: formData.provider,
          modalities: formData.modalities,
        });
        toast.success('Model created successfully');
      }
      setConfigureModalOpen(false);
      reset();
    } catch (error) {
      toast.error(`Failed to ${isEditing ? 'update' : 'create'} model`);
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6">
      <div className="flex-none flex items-start justify-between">
        <div className="mb-4">
          <h1 className="text-2xl font-semibold tracking-tight">AI Models</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage AI models and their capabilities</p>
        </div>
        <Button onClick={handleAddModel} size="sm">
          <Plus className="w-4 h-4 mr-2" />
          Add Model
        </Button>
      </div>

      <div className="flex-none">
        <FilterBar
          searchPlaceholder="Search models..."
          searchValue={search}
          onSearchChange={setSearch}
        />
      </div>

      <div className="flex-1 overflow-auto">
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
          renderItem={(model) => (
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
                        {model.provider}
                      </CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1">
                <div className="flex flex-wrap gap-2">
                  {model.modalities ? (
                    model.modalities.split(',').map(m => (
                      <Badge key={m} variant="secondary" className="text-xs">
                        {m.trim()}
                      </Badge>
                    ))
                  ) : (
                    <Badge variant="outline" className="text-xs">Text</Badge>
                  )}
                </div>
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
          )}
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
      </div>

      {/* Configure Model Modal */}
      <Dialog open={configureModalOpen} onOpenChange={setConfigureModalOpen}>
        <DialogContent className="sm:max-w-[500px]">
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
    </div>
  );
}
