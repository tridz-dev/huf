import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface HubOrchestratorStatus {
  present: boolean;
  disabled: boolean;
  provider?: string | null;
  model?: string | null;
  provider_configured: boolean;
}

export interface HubRemediation {
  code: string;
  message: string;
  action_route: string;
}

export interface HubReadiness {
  orchestrator: HubOrchestratorStatus;
  providers_with_keys: number;
  models_available: number;
  ready: boolean;
  remediation: HubRemediation[];
}

export interface HubProviderStatus {
  name: string;
  provider_name: string;
  provider_brand?: string;
  configured: boolean;
  is_local_llm: boolean;
  model_count: number;
}

export interface ModelCatalogProposal {
  model_name: string;
  provider?: string | null;
  modalities?: string;
  already_exists?: boolean;
}

// ---------------------------------------------------------------------------
// Hub readiness / provider introspection
// ---------------------------------------------------------------------------

export async function getHubReadiness(): Promise<HubReadiness> {
  const res = await call.get('huf.ai.hub_api.get_hub_readiness');
  return res.message as HubReadiness;
}

export async function getProviderStatus(): Promise<HubProviderStatus[]> {
  try {
    const res = await call.get('huf.ai.hub_api.get_provider_status');
    return (res.message as HubProviderStatus[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching provider status');
    return [];
  }
}

// ---------------------------------------------------------------------------
// Model catalog proposals (admin approval flow)
// ---------------------------------------------------------------------------

export async function getModelCatalogProposals(): Promise<ModelCatalogProposal[]> {
  try {
    const res = await call.get('huf.ai.hub_api.get_model_catalog_proposals');
    return (res.message?.proposals as ModelCatalogProposal[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching model catalog proposals');
    return [];
  }
}

export async function approveModelProposals(modelNames: string[]): Promise<void> {
  await call.post('huf.ai.hub_api.approve_model_proposals', {
    model_names: modelNames,
  });
}
