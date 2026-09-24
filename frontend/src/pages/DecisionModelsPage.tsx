import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Star, Loader2, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { PageFrame } from '@/layouts/PageFrame';
import { ProviderModelTabs } from '@/components/settings/ProviderModelTabs';
import { DecisionEmptyState } from '@/components/decision/DecisionEmptyState';
import { SetupSystemOneModal } from '@/components/decision/SetupSystemOneModal';
import { toast } from 'sonner';
import {
  listDecisionModels,
  testDeployment,
  type DecisionModel,
  type DecisionDeployment,
} from '@/services/decisionApi';
import { usePermissions } from '../contexts/PermissionsContext';
import { call } from '@/lib/frappe-sdk';

interface DeploymentWithModel extends DecisionDeployment {
  model_name?: string;
}

interface ModelGroup {
  class: string;
  families: {
    family: string;
    models: {
      model: string;
      deployments: DeploymentWithModel[];
    }[];
  }[];
}

export function DecisionModelsPage() {
  const navigate = useNavigate();
  const { hasCapability } = usePermissions();
  const isAdmin = hasCapability('decision.admin');
  const [searchParams, setSearchParams] = useSearchParams();

  const [models, setModels] = useState<DecisionModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingDeployment, setTestingDeployment] = useState<string | null>(null);
  const [deploymentUpdating, setDeploymentUpdating] = useState<string | null>(null);
  const [setupModalOpen, setSetupModalOpen] = useState(searchParams.get('setup') === '1');

  useEffect(() => {
    loadModels();
  }, []);

  useEffect(() => {
    // Sync modal state with query param
    setSetupModalOpen(searchParams.get('setup') === '1');
  }, [searchParams]);

  const loadModels = async () => {
    setLoading(true);
    try {
      const data = await listDecisionModels();
      setModels(data);
    } catch (error) {
      toast.error('Failed to load decision models');
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async (deployment: DecisionDeployment) => {
    setTestingDeployment(deployment.name);
    try {
      const result = await testDeployment(deployment.name);
      if (result.status === 'success') {
        toast.success(
          `Connection successful (${result.latency_ms}ms)`,
        );
      } else {
        toast.error(`Connection failed: ${result.error_code || 'Unknown error'}`);
      }
      // Reload to get updated health status
      await loadModels();
    } catch (error) {
      toast.error('Failed to test deployment');
    } finally {
      setTestingDeployment(null);
    }
  };

  const handleSetDefault = async (deployment: DecisionDeployment) => {
    setDeploymentUpdating(deployment.name);
    try {
      await call.post('frappe.client.set_value', {
        doctype: 'Decision Deployment',
        name: deployment.name,
        fieldname: {
          is_default_for_model: deployment.is_default_for_model ? 0 : 1,
        },
      });
      toast.success('Default deployment updated');
      await loadModels();
    } catch (error) {
      toast.error('Failed to update default deployment');
    } finally {
      setDeploymentUpdating(null);
    }
  };

  const handleToggleEnabled = async (deployment: DecisionDeployment) => {
    setDeploymentUpdating(deployment.name);
    try {
      await call.post('frappe.client.set_value', {
        doctype: 'Decision Deployment',
        name: deployment.name,
        fieldname: {
          enabled: deployment.enabled ? 0 : 1,
        },
      });
      toast.success('Deployment status updated');
      await loadModels();
    } catch (error) {
      toast.error('Failed to update deployment status');
    } finally {
      setDeploymentUpdating(null);
    }
  };

  const handleSetupSystemOne = () => {
    setSetupModalOpen(true);
    setSearchParams((params) => {
      params.set('setup', '1');
      return params;
    });
  };

  const handleSetupModalOpenChange = (open: boolean) => {
    setSetupModalOpen(open);
    if (!open) {
      setSearchParams((params) => {
        const newParams = new URLSearchParams(params);
        newParams.delete('setup');
        return newParams;
      });
    }
  };

  const handleSetupComplete = () => {
    loadModels();
  };

  const groupedModels = groupModelsByClassFamily(models);

  const hasDeployments = models.some(
    (m) => m.deployments && m.deployments.length > 0
  );

  return (
    <>
      <SetupSystemOneModal
        open={setupModalOpen}
        onOpenChange={handleSetupModalOpenChange}
        onSetup={handleSetupComplete}
      />
      <PageFrame
        title="AI providers & models"
        actions={
          isAdmin && (
            <Button onClick={handleSetupSystemOne} size="sm">
              Set up System One
            </Button>
          )
        }
        filters={<ProviderModelTabs />}
      >
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-6 w-6 animate-spin text-steel" />
        </div>
      ) : !hasDeployments ? (
        <DecisionEmptyState
          title="No decision models yet"
          description="Decision models answer bounded questions (pick one, yes/no, score) fast and cheaply."
          action={{
            label: 'Set up System One',
            onClick: handleSetupSystemOne,
          }}
          secondaryAction={{
            label: 'Use a local rules/classifier backend',
            onClick: () => navigate('/decisions/new'),
          }}
        />
      ) : (
        <div className="space-y-6">
          {groupedModels.map((classGroup) => (
            <div key={classGroup.class}>
              <div className="mb-4">
                <h2 className="font-mono text-[13px] uppercase tracking-wide text-steel font-semibold">
                  {classGroup.class}
                </h2>
              </div>

              <div className="space-y-4">
                {classGroup.families.map((familyGroup) => (
                  <div
                    key={familyGroup.family}
                    className="border border-line rounded-lg overflow-hidden"
                  >
                    <div className="bg-canvas-secondary px-4 py-3 border-b border-line">
                      <p className="font-mono text-[12px] text-steel">
                        {familyGroup.family}
                      </p>
                    </div>

                    {familyGroup.models.map((modelGroup) => (
                      <div key={modelGroup.model}>
                        <div className="px-4 py-3 border-b border-line last:border-b-0 bg-white">
                          <div className="flex items-center justify-between mb-3">
                            <p className="font-mono text-[13px] font-semibold text-ink">
                              {modelGroup.model}
                            </p>
                            <span className="text-steel text-[12px]">
                              {modelGroup.deployments.length}{' '}
                              {modelGroup.deployments.length === 1
                                ? 'deployment'
                                : 'deployments'}
                            </span>
                          </div>

                          <div className="space-y-2">
                            {modelGroup.deployments.map((deployment) => (
                              <div
                                key={deployment.name}
                                className="flex items-center gap-3 p-2 rounded bg-canvas-secondary text-[12px]"
                              >
                                <div className="flex-1 flex items-center gap-2">
                                  <span className="font-mono text-ink font-medium min-w-max">
                                    {deployment.is_default_for_model ? '★' : ' '}
                                  </span>
                                  <span className="text-ink font-medium">
                                    {deployment.deployment_name}
                                  </span>
                                  <span className="text-steel">
                                    {deployment.provider}
                                  </span>
                                  <code className="text-steel">
                                    {deployment.provider_model_id}
                                  </code>
                                </div>

                                <div className="flex items-center gap-2">
                                  {deployment.health_status && (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Badge
                                          variant={
                                            deployment.health_status === 'ok'
                                              ? 'default'
                                              : 'destructive'
                                          }
                                          className="text-[11px]"
                                        >
                                          {deployment.health_status === 'ok'
                                            ? 'ok'
                                            : 'error'}
                                        </Badge>
                                      </TooltipTrigger>
                                      <TooltipContent>
                                        {deployment.last_healthcheck
                                          ? `Last checked: ${deployment.last_healthcheck}`
                                          : 'Not checked yet'}
                                      </TooltipContent>
                                    </Tooltip>
                                  )}

                                  <Switch
                                    checked={Boolean(deployment.enabled)}
                                    onCheckedChange={() =>
                                      handleToggleEnabled(deployment)
                                    }
                                    disabled={
                                      deploymentUpdating === deployment.name
                                    }
                                  />

                                  {isAdmin && (
                                    <>
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() =>
                                              handleSetDefault(deployment)
                                            }
                                            disabled={
                                              deploymentUpdating ===
                                              deployment.name
                                            }
                                          >
                                            <Star
                                              className={`h-4 w-4 ${
                                                deployment.is_default_for_model
                                                  ? 'fill-signal'
                                                  : ''
                                              }`}
                                            />
                                          </Button>
                                        </TooltipTrigger>
                                        <TooltipContent>
                                          Set as default
                                        </TooltipContent>
                                      </Tooltip>

                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() =>
                                          handleTestConnection(deployment)
                                        }
                                        disabled={
                                          testingDeployment === deployment.name
                                        }
                                      >
                                        {testingDeployment ===
                                        deployment.name ? (
                                          <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                          <Zap className="h-4 w-4" />
                                        )}
                                      </Button>
                                    </>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      </PageFrame>
    </>
  );
}

function groupModelsByClassFamily(models: DecisionModel[]): ModelGroup[] {
  const grouped: Record<string, Record<string, Record<string, DecisionDeployment[]>>> = {};

  models.forEach((model) => {
    const modelClass = extractClass(model.model_key) || 'Other';
    const family = model.family || 'Other';
    const modelName = model.model_name || 'Unknown';

    if (!grouped[modelClass]) {
      grouped[modelClass] = {};
    }
    if (!grouped[modelClass][family]) {
      grouped[modelClass][family] = {};
    }
    if (!grouped[modelClass][family][modelName]) {
      grouped[modelClass][family][modelName] = [];
    }

    if (model.deployments) {
      grouped[modelClass][family][modelName].push(...model.deployments);
    }
  });

  return Object.entries(grouped).map(([classKey, families]) => ({
    class: classKey,
    families: Object.entries(families).map(([family, models]) => ({
      family,
      models: Object.entries(models).map(([model, deployments]) => ({
        model,
        deployments,
      })),
    })),
  }));
}

function extractClass(modelKey: string): string {
  // Extract the class from the model key (e.g., "jev-1.13-free" -> "System One")
  if (modelKey.startsWith('jev')) return 'System One';
  if (modelKey.startsWith('local')) return 'Local Rules';
  if (modelKey.startsWith('classifier')) return 'Classifier';
  if (modelKey.startsWith('similarity')) return 'Similarity';
  return 'Other';
}
