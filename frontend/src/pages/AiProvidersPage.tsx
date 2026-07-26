import { ArrowRight, Check, ExternalLink, KeyRound, Loader2, Settings, Sparkles } from 'lucide-react';
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
import { createModel, getModels, getProvider, getProviders, updateProvider, createProvider } from '../services/providerApi';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import type { AIProvider, AIModel } from '../types/agent.types';
import { ProviderBrandSelect } from '@/components/providers/ProviderBrandSelect';
import { ProviderBrandIcon } from '@/components/providers/ProviderBrandIcon';
import { suggestBrandFromProviderName, resolveProviderBrand } from '@/utils/providerBrands';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

interface AiProvidersPageProps {
  addProviderKey?: number;
}

type StarterPath = 'openrouter' | 'google';

const STARTER_PATHS: Record<StarterPath, {
  providerName: string;
  providerBrand: string;
  modelName: string;
  title: string;
  description: string;
  caution: string;
  signupUrl: string;
  signupLabel: string;
  freePricing: boolean;
}> = {
  openrouter: {
    providerName: 'OpenRouter',
    providerBrand: 'openrouter',
    modelName: 'openrouter/free',
    title: 'Try OpenRouter Free',
    description: 'Start with a zero-cost router that selects an available free model for each request.',
    caution: 'Best for learning and demos. Free models can change, have lower limits, and are not a production reliability tier.',
    signupUrl: 'https://openrouter.ai/keys',
    signupLabel: 'Get an OpenRouter key',
    freePricing: true,
  },
  google: {
    providerName: 'Google',
    providerBrand: 'google',
    modelName: 'gemini-2.5-flash',
    title: 'Try Gemini with Google AI Studio',
    description: 'Use Gemini 2.5 Flash with the Google Gemini API free tier to explore Huf.',
    caution: 'Free-tier limits apply. Google states that free-tier content may be used to improve its products; avoid sensitive production data.',
    signupUrl: 'https://aistudio.google.com/app/apikey',
    signupLabel: 'Get a Google AI Studio key',
    freePricing: false,
  },
};

export function AiProvidersPage({ addProviderKey }: AiProvidersPageProps) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const configureHandledRef = useRef(false);
  const [models, setModels] = useState<AIModel[]>([]);
  const [configureModalOpen, setConfigureModalOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<AIProvider | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingProvider, setLoadingProvider] = useState(false);
  const [saving, setSaving] = useState(false);
  const [starterPath, setStarterPath] = useState<StarterPath | null>(null);
  const [completedStarter, setCompletedStarter] = useState<StarterPath | null>(null);
  const [starterApiKey, setStarterApiKey] = useState('');
  const [starterSaving, setStarterSaving] = useState(false);
  const [formData, setFormData] = useState({
    provider_name: '',
    api_key: '',
    provider_brand: '',
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
      const modelsArray: AIModel[] = Array.isArray(modelsData) ? modelsData : (modelsData as { items: AIModel[] }).items;
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
    setFormData({
      provider_name: '',
      api_key: '',
      provider_brand: '',
    });
    setConfigureModalOpen(true);
  };

  // Listen for add provider trigger from header
  useEffect(() => {
    if (addProviderKey && addProviderKey > 0) {
      handleAddProvider();
    }
     
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
        provider_brand: details.provider_brand || '',
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
        });
        toast.success('Provider updated successfully');
      } else {
        await createProvider({
          provider_name: formData.provider_name.trim(),
          api_key: formData.api_key,
          provider_brand: providerBrand,
        });
        toast.success('Provider created successfully');
      }
      setConfigureModalOpen(false);
      // Reset form
      setFormData({
        provider_name: '',
        api_key: '',
        provider_brand: '',
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

  const handleStarterSetup = async () => {
    if (!starterPath || !starterApiKey.trim()) {
      toast.error('Enter an API key to continue');
      return;
    }

    const starter = STARTER_PATHS[starterPath];
    setStarterSaving(true);
    try {
      const providersResponse = await getProviders({ limit: 100 });
      const allProviders = Array.isArray(providersResponse) ? providersResponse : providersResponse.items;
      const existingProvider = allProviders.find(
        (provider) => provider.provider_name.toLowerCase() === starter.providerName.toLowerCase(),
      );
      const provider = existingProvider
        ? await updateProvider(existingProvider.name, {
            api_key: starterApiKey.trim(),
            provider_brand: starter.providerBrand,
          })
        : await createProvider({
            provider_name: starter.providerName,
            api_key: starterApiKey.trim(),
            provider_brand: starter.providerBrand,
          });

      const currentModels = await getModels();
      const modelExists = currentModels.some(
        (model) => model.model_name === starter.modelName && model.provider === provider.name,
      );
      if (!modelExists) {
        await createModel({
          model_name: starter.modelName,
          provider: provider.name,
          modalities: 'Text',
          use_custom_pricing: starter.freePricing ? 1 : 0,
          input_cost_per_1m_tokens: starter.freePricing ? 0 : null,
          output_cost_per_1m_tokens: starter.freePricing ? 0 : null,
        });
      }

      toast.success(`${starter.providerName} is ready`, {
        description: `You can now create an agent with ${starter.modelName}. The key has not been tested yet.`,
      });
      setCompletedStarter(starterPath);
      setStarterPath(null);
      setStarterApiKey('');
      reset();
      const refreshedModels = await getModels();
      setModels(refreshedModels);
    } catch (setupError) {
      toast.error('Could not finish starter setup', {
        description: 'Huf could not save this starter setup. Check the details and try again.',
      });
      console.error(setupError);
    } finally {
      setStarterSaving(false);
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
      <Card className="border-primary/20 bg-primary/5">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2 text-primary">
            <Sparkles className="h-4 w-4" />
            <CardTitle className="text-base">Get started with AI</CardTitle>
          </div>
          <CardDescription>
            Pick a free-friendly starter path, add its key, and Huf will prepare a model for your first agent.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row">
          {completedStarter ? (
            <div className="flex w-full flex-col gap-3 rounded-md border border-primary/20 bg-background/60 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">Your {STARTER_PATHS[completedStarter].providerName} starter is ready</p>
                  <p className="text-xs text-muted-foreground">Next, create an agent and choose {STARTER_PATHS[completedStarter].modelName}.</p>
                </div>
              </div>
              <Button className="shrink-0" onClick={() => navigate('/agents/new')}>
                Create your first agent<ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          ) : (Object.entries(STARTER_PATHS) as [StarterPath, typeof STARTER_PATHS[StarterPath]][]).map(([path, starter]) => (
            <Button key={path} variant="outline" className="h-auto flex-1 justify-between whitespace-normal text-left" onClick={() => setStarterPath(path)}>
              <span>
                <span className="block font-medium">{starter.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{starter.modelName}</span>
              </span>
              <ArrowRight className="ml-3 h-4 w-4 shrink-0" />
            </Button>
          ))}
        </CardContent>
      </Card>
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
                <Label htmlFor="api_key">API Key</Label>
                <Input
                  id="api_key"
                  type="password"
                  placeholder="Enter API key"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                />
              </div>

              <ProviderBrandSelect
                value={formData.provider_brand}
                onChange={(provider_brand) => setFormData({ ...formData, provider_brand })}
                providerName={formData.provider_name}
                required
              />
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

      <Dialog open={starterPath !== null} onOpenChange={(open) => !open && setStarterPath(null)}>
        <DialogContent className="sm:max-w-[520px]">
          {starterPath && (() => {
            const starter = STARTER_PATHS[starterPath];
            return <>
              <DialogHeader>
                <DialogTitle>{starter.title}</DialogTitle>
                <DialogDescription>{starter.description}</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
                  <strong className="text-foreground">Good to know: </strong>{starter.caution}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="starter-api-key">API key</Label>
                  <Input id="starter-api-key" type="password" autoComplete="off" placeholder="Paste your API key" value={starterApiKey} onChange={(event) => setStarterApiKey(event.target.value)} />
                  <a className="inline-flex items-center gap-1 text-sm text-primary hover:underline" href={starter.signupUrl} target="_blank" rel="noreferrer">
                    {starter.signupLabel}<ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </div>
                <div className="rounded-md border p-3 text-sm">
                  <p className="font-medium">Huf will configure</p>
                  <p className="mt-1 text-muted-foreground">Provider: {starter.providerName} · Model: <code>{starter.modelName}</code></p>
                  <p className="mt-2 flex items-center gap-1 text-muted-foreground"><Check className="h-4 w-4 text-primary" /> Your key is stored in Huf's encrypted password field.</p>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setStarterPath(null)} disabled={starterSaving}>Cancel</Button>
                <Button onClick={handleStarterSetup} disabled={starterSaving || !starterApiKey.trim()}>
                  {starterSaving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Setting up…</> : <><KeyRound className="mr-2 h-4 w-4" />Set up starter</>}
                </Button>
              </DialogFooter>
            </>;
          })()}
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
