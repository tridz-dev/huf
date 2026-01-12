import { Plug, Settings, Loader2 } from 'lucide-react';
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
import { PageLayout, FilterBar, GridView, LoadMoreButton } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getProviders, getProvider, updateProvider, createProvider } from '../services/providerApi';
import { getModels } from '../services/providerApi';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import type { AIProvider, AIModel } from '../types/agent.types';

interface IntegrationsPageProps {
  addProviderKey?: number;
}

export function IntegrationsPage({ addProviderKey }: IntegrationsPageProps) {
  const [models, setModels] = useState<AIModel[]>([]);
  const [configureModalOpen, setConfigureModalOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<AIProvider | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingProvider, setLoadingProvider] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    provider_name: '',
    api_key: '',
    slug: '',
    chef: '',
  });

  const {
    items: providers,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
    reset,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    AIProvider
  >({
    fetchFn: async (params) => {
      const response = await getProviders({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      // Handle both old (array) and new (paginated) response formats
      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      // Convert PaginatedProvidersResponse to PaginatedResponse format
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

  // Fetch all models once to get model counts
  useEffect(() => {
    getModels().then((modelsData) => {
      setModels(modelsData);
    });
  }, []);

  const getModelCountForProvider = (providerName: string) => {
    return models.filter(m => m.provider === providerName).length;
  };

  const handleAddProvider = () => {
    setSelectedProvider(null);
    setIsEditing(false);
    setFormData({
      provider_name: '',
      api_key: '',
      slug: '',
      chef: '',
    });
    setConfigureModalOpen(true);
  };

  // Listen for add provider trigger from header
  useEffect(() => {
    if (addProviderKey && addProviderKey > 0) {
      handleAddProvider();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addProviderKey]);

  const handleConfigure = async (provider: AIProvider) => {
    setSelectedProvider(provider);
    setIsEditing(true);
    setConfigureModalOpen(true);
    setLoadingProvider(true);
    
    try {
      const details = await getProvider(provider.name);
      setFormData({
        provider_name: details.provider_name || '',
        api_key: details.api_key || '',
        slug: details.slug || '',
        chef: details.chef || '',
      });
    } catch (error) {
      toast.error('Failed to load provider details');
      console.error(error);
    } finally {
      setLoadingProvider(false);
    }
  };

  const handleSave = async () => {
    // Validate provider name is required
    if (!isEditing && !formData.provider_name.trim()) {
      toast.error('Provider name is required');
      return;
    }

    setSaving(true);
    try {
      if (isEditing && selectedProvider) {
        // Update existing provider
        await updateProvider(selectedProvider.name, {
          api_key: formData.api_key,
          slug: formData.slug,
          chef: formData.chef,
        });
        toast.success('Provider updated successfully');
      } else {
        // Create new provider
        await createProvider({
          provider_name: formData.provider_name.trim(),
          api_key: formData.api_key,
          slug: formData.slug,
          chef: formData.chef,
        });
        toast.success('Provider created successfully');
      }
      setConfigureModalOpen(false);
      // Reset form
      setFormData({
        provider_name: '',
        api_key: '',
        slug: '',
        chef: '',
      });
      // Refresh the list
      reset();
    } catch (error) {
      toast.error(`Failed to ${isEditing ? 'update' : 'create'} provider`);
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageLayout
        subtitle="Connect AI providers and external services"
        filters={
        <FilterBar
          searchPlaceholder="Search providers..."
          searchValue={search}
          onSearchChange={setSearch}
        />
      }
    >
      <GridView
        items={providers}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No providers found.</p>
          </div>
        }
        renderItem={(provider) => {
          const providerModels = models.filter(m => m.provider === provider.name);
          return (
            <Card key={provider.name} className="h-full flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                      <Plug className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{provider.provider_name}</CardTitle>
                      <CardDescription className="text-xs">
                        {getModelCountForProvider(provider.name)} models
                      </CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1">
                {providerModels.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {providerModels.slice(0, 3).map(model => (
                      <Badge key={model.name} variant="secondary" className="text-xs">
                        {model.model_name}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No models configured</p>
                )}
              </CardContent>
              <CardFooter>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="flex-1 gap-2"
                  onClick={() => handleConfigure(provider)}
                >
                  <Settings className="w-4 h-4" />
                  Configure
                </Button>
              </CardFooter>
            </Card>
          );
        }}
        keyExtractor={(provider) => provider.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && providers.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} providers` : 'No more providers to load'}
        </div>
      )}

      {/* Configure Provider Modal */}
      <Dialog open={configureModalOpen} onOpenChange={setConfigureModalOpen}>
        <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto min-h-[500px]">
          <DialogHeader>
            <DialogTitle>
              {isEditing ? `Configure ${selectedProvider?.provider_name || 'Provider'}` : 'Add Provider'}
            </DialogTitle>
            <DialogDescription>
              {isEditing ? 'Update provider configuration settings' : 'Create a new AI provider'}
            </DialogDescription>
          </DialogHeader>

          {loadingProvider ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-4 py-4">
              {!isEditing && (
                <div className="space-y-2">
                  <Label htmlFor="provider_name">
                    Provider Name <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="provider_name"
                    type="text"
                    placeholder="Enter provider name (e.g., OpenAI, Anthropic)"
                    value={formData.provider_name}
                    onChange={(e) => setFormData({ ...formData, provider_name: e.target.value })}
                    required
                  />
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="api_key">API Key</Label>
                <Input
                  id="api_key"
                  type="password"
                  placeholder="Enter API key"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="slug">Slug</Label>
                <Input
                  id="slug"
                  type="text"
                  placeholder="Enter slug"
                  value={formData.slug}
                  onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="chef">Chef</Label>
                <Input
                  id="chef"
                  type="text"
                  placeholder="Enter chef"
                  value={formData.chef}
                  onChange={(e) => setFormData({ ...formData, chef: e.target.value })}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfigureModalOpen(false)}
              disabled={saving || loadingProvider}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || loadingProvider}
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
