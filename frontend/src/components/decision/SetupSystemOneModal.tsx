import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
  DialogClose,
} from '@/components/ui/dialog';
import {
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  getSetupCatalog,
  setupDeployment,
  type SetupCatalogEntry,
  type SetupDeploymentResult,
} from '@/services/decisionApi';
import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

interface SetupSystemOneModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSetup?: () => void;
}

interface ProviderOption {
  brand: string;
  hasKey: boolean;
}

export function SetupSystemOneModal({
  open,
  onOpenChange,
  onSetup,
}: SetupSystemOneModalProps) {
  const navigate = useNavigate();

  // Step tracking
  const [step, setStep] = useState<'provider' | 'model' | 'confirm' | 'done'>('provider');
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<SetupCatalogEntry[]>([]);
  const [providers, setProviders] = useState<ProviderOption[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<SetupCatalogEntry | null>(null);
  const [setupResult, setSetupResult] = useState<SetupDeploymentResult | null>(null);

  // Load catalog and providers when modal opens
  useEffect(() => {
    if (open && step === 'provider') {
      loadCatalogAndProviders();
    }
  }, [open, step]);

  const loadCatalogAndProviders = async () => {
    setLoading(true);
    try {
      const catalogData = await getSetupCatalog();
      setCatalog(catalogData);

      // Extract unique provider brands
      const brands = Array.from(
        new Set(catalogData.map((entry) => entry.provider_brand))
      );

      // Check which providers have keys
      const providerOptions: ProviderOption[] = [];
      for (const brand of brands) {
        try {
          // Query AI Provider by provider_brand to check if it has a key
          const result = await call.get('frappe.client.get_list', {
            doctype: 'AI Provider',
            filters: { provider_brand: brand },
            fields: ['name', 'provider_brand', 'api_key'],
            limit_page_length: 1,
          });

          const providers = result.message as Array<{ name: string; provider_brand: string; api_key?: string }> | undefined;
          const provider = providers?.[0];
          if (provider) {
            providerOptions.push({
              brand: provider.name, // Use the docname (provider identifier)
              hasKey: !!provider.api_key,
            });
          }
        } catch (error) {
          console.error(`Failed to check provider ${brand}:`, error);
          // Still add the provider option even if we can't check the key
          const firstCatalogProvider = catalogData.find(
            (e) => e.provider_brand === brand
          );
          if (firstCatalogProvider) {
            providerOptions.push({
              brand,
              hasKey: false,
            });
          }
        }
      }

      setProviders(providerOptions);
    } catch (error) {
      handleFrappeError(error, 'Failed to load setup catalog');
    } finally {
      setLoading(false);
    }
  };

  const handleAddKey = (brand: string) => {
    // Find the provider docname from the brand
    const provider = providers.find((p) => p.brand === brand);
    if (provider) {
      // Open the provider edit page in a new tab
      window.open(`/app/ai-provider/${encodeURIComponent(provider.brand)}`, '_blank');

      // Set up a check to see if the key was added
      // After a small delay, offer to refresh or continue
      const checkInterval = setInterval(() => {
        setStep('provider');
        clearInterval(checkInterval);
      }, 1000);
    }
  };

  const handleProviderSelect = (brand: string) => {
    const provider = providers.find((p) => p.brand === brand);
    if (provider && provider.hasKey) {
      setSelectedProvider(brand);
      setStep('model');
    } else if (provider) {
      handleAddKey(brand);
    }
  };

  const getModelsForProvider = (): SetupCatalogEntry[] => {
    if (!selectedProvider) return [];
    return catalog.filter((entry) => entry.provider_brand === selectedProvider);
  };

  const handleModelSelect = (model: SetupCatalogEntry) => {
    setSelectedModel(model);
    setStep('confirm');
  };

  const handleConfirm = async () => {
    if (!selectedProvider || !selectedModel) {
      toast.error('Please select a provider and model');
      return;
    }

    setLoading(true);
    try {
      const result = await setupDeployment(selectedProvider, selectedModel.model_name);
      setSetupResult(result);
      setStep('done');

      if (result.probe.status === 'success') {
        toast.success('System One deployment created successfully');
      } else {
        toast.warning(
          `Deployment created but connection test failed: ${result.probe.error_code || 'Unknown error'}`
        );
      }
    } catch (error) {
      handleFrappeError(error, 'Failed to set up deployment');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    onOpenChange(false);
    setStep('provider');
    setSelectedProvider(null);
    setSelectedModel(null);
    setSetupResult(null);
    setCatalog([]);
  };

  const handleDone = () => {
    handleClose();
    if (onSetup) {
      onSetup();
    }
  };

  const handlePlayground = () => {
    if (setupResult?.ai_model) {
      handleClose();
      navigate(`/playground?mode=decision&model=${encodeURIComponent(setupResult.ai_model)}`);
    }
  };

  const handleAgents = () => {
    handleClose();
    navigate('/app/agent');
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="max-w-md">
        <DialogScrollHeader>
          <DialogTitle>
            {step === 'provider' && 'Select Provider'}
            {step === 'model' && 'Choose Model'}
            {step === 'confirm' && 'Confirm Setup'}
            {step === 'done' && 'Setup Complete'}
          </DialogTitle>
          <DialogDescription>
            {step === 'provider' &&
              'Choose an AI provider with an API key to deploy System One'}
            {step === 'model' &&
              `Available models for ${selectedProvider}`}
            {step === 'confirm' &&
              'Review your System One deployment configuration'}
            {step === 'done' && 'Your System One deployment is ready to use'}
          </DialogDescription>
          <DialogClose />
        </DialogScrollHeader>

        <div className="space-y-4 px-6 py-4">
          {step === 'provider' && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Select a provider with an API key configured to deploy System One. If you don't see your provider, add an API key first.
              </p>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-steel" />
                </div>
              ) : providers.length === 0 ? (
                <div className="rounded-lg border border-destructive bg-destructive/5 p-3 text-sm text-destructive">
                  <AlertCircle className="mb-2 h-4 w-4 inline mr-2" />
                  No providers found in the catalog. Contact your administrator.
                </div>
              ) : (
                providers.map((provider) => (
                  <button
                    key={provider.brand}
                    onClick={() => handleProviderSelect(provider.brand)}
                    className="w-full text-left p-3 rounded-lg border border-line hover:bg-canvas-secondary transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-ink">{provider.brand}</span>
                      {provider.hasKey ? (
                        <Badge variant="default" className="text-xs">
                          Ready
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs">
                          Add key
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-steel mt-1">
                      {provider.hasKey
                        ? 'API key configured'
                        : 'Click to add API key'}
                    </p>
                  </button>
                ))
              )}
            </div>
          )}

          {step === 'model' && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Select a model to deploy. Each model includes a wire protocol and endpoint configuration.
              </p>
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-steel" />
                </div>
              ) : (
                getModelsForProvider().map((model) => (
                  <button
                    key={model.model_name}
                    onClick={() => handleModelSelect(model)}
                    className="w-full text-left p-3 rounded-lg border border-line hover:bg-canvas-secondary transition-colors"
                  >
                    <div className="space-y-1">
                      <p className="font-medium text-ink">{model.model_name}</p>
                      <p className="text-xs text-steel">
                        Canonical: {model.canonical_model}
                      </p>
                      <p className="text-xs text-steel">
                        Protocol: {model.wire_protocol}
                      </p>
                    </div>
                  </button>
                ))
              )}
            </div>
          )}

          {step === 'confirm' && selectedModel && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Review your configuration below. A connection test will run automatically. If successful, your deployment will be enabled and ready to use.
              </p>
              <div className="rounded-lg bg-canvas-secondary p-3 space-y-2 text-sm">
                <div>
                  <p className="text-steel">Provider</p>
                  <p className="font-medium text-ink">{selectedProvider}</p>
                </div>
                <div>
                  <p className="text-steel">Model</p>
                  <p className="font-medium text-ink">{selectedModel.model_name}</p>
                </div>
                <div>
                  <p className="text-steel">Canonical Model</p>
                  <p className="font-medium text-ink">
                    {selectedModel.canonical_model}
                  </p>
                </div>
                <div>
                  <p className="text-steel">Wire Protocol</p>
                  <p className="font-medium text-ink">{selectedModel.wire_protocol}</p>
                </div>
              </div>
            </div>
          )}

          {step === 'done' && setupResult && (
            <div className="space-y-4">
              <div
                className={`rounded-lg p-3 text-sm ${
                  setupResult.probe.status === 'success'
                    ? 'bg-success/10 border border-success text-success'
                    : 'bg-destructive/10 border border-destructive text-destructive'
                }`}
              >
                <div className="flex items-start gap-2">
                  {setupResult.probe.status === 'success' ? (
                    <CheckCircle2 className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  )}
                  <div>
                    <p className="font-medium">
                      {setupResult.probe.status === 'success'
                        ? 'Connection successful'
                        : 'Connection failed'}
                    </p>
                    <p className="text-xs mt-1">
                      {setupResult.probe.status === 'success'
                        ? `Latency: ${setupResult.probe.latency_ms}ms`
                        : `Error: ${setupResult.probe.error_code || 'Unknown error'}`}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-lg bg-canvas-secondary p-3 space-y-2 text-sm">
                <div>
                  <p className="text-steel">Deployment</p>
                  <p className="font-mono text-xs text-ink">
                    {setupResult.deployment}
                  </p>
                </div>
                <div>
                  <p className="text-steel">AI Model</p>
                  <p className="font-mono text-xs text-ink">
                    {setupResult.ai_model}
                  </p>
                </div>
              </div>

              <p className="text-xs text-muted-foreground">
                Your System One deployment is ready to use. Try it in the
                Playground or add it to an Agent.
              </p>
            </div>
          )}
        </div>

        <DialogScrollFooter className="px-6 py-4 border-t border-line">
          {step === 'provider' && (
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
          )}

          {step === 'model' && (
            <>
              <Button variant="outline" onClick={() => setStep('provider')}>
                Back
              </Button>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
            </>
          )}

          {step === 'confirm' && (
            <>
              <Button variant="outline" onClick={() => setStep('model')}>
                Back
              </Button>
              <Button onClick={handleConfirm} disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Setting up...
                  </>
                ) : (
                  'Confirm & Test'
                )}
              </Button>
            </>
          )}

          {step === 'done' && (
            <>
              <Button variant="outline" onClick={handleDone}>
                Close
              </Button>
              <Button onClick={handlePlayground} variant="default">
                Try in Playground
              </Button>
              <Button onClick={handleAgents} variant="secondary">
                Go to Agents
              </Button>
            </>
          )}
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
