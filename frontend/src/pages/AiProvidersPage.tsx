import { Settings, Loader2, CheckCircle2, XCircle } from 'lucide-react';
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
import { Checkbox } from '../components/ui/checkbox';
import { PageLayout, FilterBar, GridView, LoadMoreButton } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getProviders, getProvider, updateProvider, createProvider, testProviderConnection } from '../services/providerApi';
import { getModels } from '../services/providerApi';
import type { ProviderConnectionTestResult } from '../services/providerApi';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import type { AIProvider, AIModel } from '../types/agent.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { ProviderBrandSelect } from '@/components/providers/ProviderBrandSelect';
import { ProviderBrandIcon } from '@/components/providers/ProviderBrandIcon';
import { suggestBrandFromProviderName, resolveProviderBrand } from '@/utils/providerBrands';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

interface AiProvidersPageProps {
  addProviderKey?: number;
}

export function AiProvidersPage({ addProviderKey }: AiProvidersPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const configureHandledRef = useRef(false);
  const [models, setModels] = useState<AIModel[]>([]);
  const [configureModalOpen, setConfigureModalOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<AIProvider | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingProvider, setLoadingProvider] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    provider_name: '',
    api_key: '',
    provider_brand: '',
    is_local_llm: false,
    api_base_url: '',
  });
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionTest, setConnectionTest] = useState<ProviderConnectionTestResult | null>(null);

  const emptyFormData = {
    provider_name: '',
    api_key: '',
    provider_brand: '',
    is_local_llm: false,
    api_base_url: '',
  };

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
    error,
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

  // Show error toast when there's an error
  useEffect(() => {
    if (error) {
      toast.error('Failed to load providers', {
        description: error.message || 'An error occurred while fetching providers. Please try again.',
        duration: 5000,
      });
    }
  }, [error]);

  useEffect(() => {
    getModels().then((modelsData) => {
      const modelsArray: AIModel[] = Array.isArray(modelsData)
        ? modelsData
        : ((modelsData as { items?: AIModel[] }).items ?? []);
      setModels(modelsArray);
    }).catch((error) => {
      console.error('Error fetching models:', error);
      toast.error('Failed to load models', {
        description: error instanceof Error ? error.message : 'An error occurred while fetching models.',
        duration: 5000,
      });
    });
  }, []);

  const getModelCountForProvider = (providerName: string) => {
    return models.filter(m => m.provider === providerName).length;
  };

  const handleAddProvider = () => {
    setSelectedProvider(null);
    setIsEditing(false);
    setConnectionTest(null);
    setFormData({ ...emptyFormData });
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
    setConnectionTest(null);

    try {
      const details = await getProvider(provider.name);
      setFormData({
        provider_name: details.provider_name || '',
        api_key: details.api_key || '',
        provider_brand: details.provider_brand || '',
        is_local_llm: details.is_local_llm === 1,
        api_base_url: details.api_base_url || '',
      });
    } catch (error) {
      toast.error('Failed to load provider details');
      console.error(error);
    } finally {
      setLoadingProvider(false);
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
        const listMatch = providers.find((provider) => provider.name === configureId);
        if (listMatch) {
          await handleConfigure(listMatch);
        } else {
          const details = await getProvider(configureId);
          await handleConfigure(details);
        }
      } catch (loadError) {
        if (!cancelled) {
          toast.error('Failed to open provider configuration');
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

  const handleSave = async () => {
    // Validate provider name is required
    if (!isEditing && !formData.provider_name.trim()) {
      toast.error('Provider name is required');
      return;
    }

    // Local providers need an endpoint URL instead of an API key
    if (formData.is_local_llm && !formData.api_base_url.trim()) {
      toast.error('API Base URL is required for local providers');
      return;
    }

    const providerBrand =
      formData.provider_brand ||
      suggestBrandFromProviderName(formData.provider_name) ||
      'other';

    setSaving(true);
    try {
      if (isEditing && selectedProvider) {
        await updateProvider(selectedProvider.name, {
          api_key: formData.api_key,
          provider_brand: providerBrand,
          is_local_llm: formData.is_local_llm ? 1 : 0,
          api_base_url: formData.api_base_url.trim(),
        });
        toast.success('Provider updated successfully');
      } else {
        await createProvider({
          provider_name: formData.provider_name.trim(),
          api_key: formData.api_key,
          provider_brand: providerBrand,
          is_local_llm: formData.is_local_llm ? 1 : 0,
          api_base_url: formData.api_base_url.trim(),
        });
        toast.success('Provider created successfully');
      }
      setConfigureModalOpen(false);
      // Reset form
      setFormData({ ...emptyFormData });
      // Refresh the list
      reset();
    } catch (error) {
      toast.error(`Failed to ${isEditing ? 'update' : 'create'} provider`, {
        description: getFrappeErrorMessage(error),
        duration: 8000,
      });
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    if (!selectedProvider) return;

    setTestingConnection(true);
    setConnectionTest(null);
    try {
      const result = await testProviderConnection(selectedProvider.name);
      setConnectionTest(result);
    } catch (error) {
      toast.error('Connection test failed', {
        description: getFrappeErrorMessage(error),
        duration: 8000,
      });
      console.error(error);
    } finally {
      setTestingConnection(false);
    }
  };

  useSaveShortcut({
    onSave: handleSave,
    enabled: configureModalOpen && !loadingProvider,
    isSubmitting: saving,
    allowInDialog: true,
  });

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
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load providers</p>
          <p className="text-sm text-steel mb-4">{error.message || 'An error occurred while fetching providers.'}</p>
        </div>
      )}
      <GridView
        items={providers}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="font-body text-steel-soft mb-4">No providers found.</p>
          </div>
        }
        renderItem={(provider) => {
          const providerModels = models.filter(m => m.provider === provider.name);
          return (
            <Card key={provider.name} className="h-full flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <ProviderBrandIcon
                      brand={resolveProviderBrand(provider.provider_brand, provider.provider_name)}
                      size="sm"
                      showFallback
                    />
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
                        {model.modalities ? ` · ${model.modalities}` : ''}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm font-body text-steel-soft">No models configured</p>
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
        <div className="text-center py-4 text-sm font-body text-steel">
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
              <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
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
                <Label htmlFor="api_key">
                  {formData.is_local_llm ? 'API Key (optional for local)' : 'API Key'}
                </Label>
                <Input
                  id="api_key"
                  type="password"
                  placeholder="Enter API key"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                />
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="is_local_llm"
                  checked={formData.is_local_llm}
                  onCheckedChange={(checked) =>
                    setFormData({ ...formData, is_local_llm: checked === true })
                  }
                />
                <Label htmlFor="is_local_llm" className="font-normal cursor-pointer">
                  Is Local LLM (self-hosted endpoint)
                </Label>
              </div>

              {formData.is_local_llm && (
                <div className="space-y-2">
                  <Label htmlFor="api_base_url">
                    API Base URL <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="api_base_url"
                    type="text"
                    placeholder="http://host.docker.internal:11434"
                    value={formData.api_base_url}
                    onChange={(e) => setFormData({ ...formData, api_base_url: e.target.value })}
                  />
                </div>
              )}

              <ProviderBrandSelect
                value={formData.provider_brand}
                onChange={(provider_brand) => setFormData({ ...formData, provider_brand })}
                providerName={formData.provider_name}
                required
              />

              {isEditing && (
                <div className="space-y-3 rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="text-sm">Connection</Label>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleTestConnection}
                      disabled={testingConnection || saving}
                    >
                      {testingConnection ? (
                        <>
                          <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                          Testing...
                        </>
                      ) : (
                        'Test Connection'
                      )}
                    </Button>
                  </div>
                  {connectionTest && (
                    <div className="space-y-2 text-sm">
                      <div className="flex items-start gap-2">
                        {connectionTest.provider.ok ? (
                          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-green-600" />
                        ) : (
                          <XCircle className="w-4 h-4 mt-0.5 shrink-0 text-destructive" />
                        )}
                        <div className="min-w-0">
                          <span className={connectionTest.provider.ok ? 'text-green-700' : 'text-destructive'}>
                            {connectionTest.provider.ok ? 'Endpoint reachable' : 'Endpoint unreachable'}
                          </span>
                          {connectionTest.provider.error && (
                            <p className="text-xs text-destructive break-words">{connectionTest.provider.error}</p>
                          )}
                        </div>
                      </div>
                      {connectionTest.models.map((model) => (
                        <div key={model.name} className="flex items-start gap-2">
                          {model.ok ? (
                            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-green-600" />
                          ) : (
                            <XCircle className="w-4 h-4 mt-0.5 shrink-0 text-destructive" />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-1">
                              <span className="font-medium">{model.name}</span>
                              {model.capabilities?.map((cap) => (
                                <Badge key={cap} variant="secondary" className="text-xs">
                                  {cap}
                                </Badge>
                              ))}
                            </div>
                            {model.error && (
                              <p className="text-xs text-destructive break-words">{model.error}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
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
