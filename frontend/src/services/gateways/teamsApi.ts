import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export type TeamsCheckStatus = 'pass' | 'warn' | 'fail' | 'info';

export interface TeamsCheck {
  id: string;
  status: TeamsCheckStatus;
  title: string;
  detail: string;
  how_to_fix: string;
}

export interface TeamsDiagnosis {
  gateway: string;
  checks: TeamsCheck[];
  summary: Record<TeamsCheckStatus, number>;
}

export interface TeamsSettings {
  allowed_tenants: string;
  allowed_tenant_list: string[];
  app_package_version?: string;
  bot_handle?: string;
  private_output_policy?: TeamsPrivateOutputPolicy;
  help_text_override?: string;
}

export type TeamsPrivateOutputPolicy = 'Always private' | 'Private when records touched' | 'Channel';

export interface TeamsBotSettingsInput {
  bot_handle: string;
  private_output_policy: TeamsPrivateOutputPolicy;
  help_text_override: string;
}

export interface TeamsLink {
  name: string;
  gateway: string;
  team_id: string | null;
  external_id: string;
  user: string;
  state: string;
  source: string;
  display_label: string | null;
  linked_at: string | null;
}

const DIAG = 'huf.ai.gateways.teams.diagnostics';
const TENANT = 'huf.ai.gateways.teams.tenant';
const IDENTITY = 'huf.ai.gateways.teams.identity';
const MANIFEST = 'huf.ai.gateways.teams.manifest';

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const DEFAULT_PACKAGE_VERSION = '1.0.0';
const VERSION_RE = /^\d+\.\d+\.\d+$/;

export function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function isGuid(value: string): boolean {
  return GUID_RE.test(value.trim().toLowerCase());
}

export interface TenantParseResult {
  tenants: string[];
  invalid: string[];
}

/** Split newline/comma/semicolon separated text into unique lowercase GUIDs; keeps non-GUID entries aside. */
export function parseTenantText(text: string): TenantParseResult {
  const tenants: string[] = [];
  const invalid: string[] = [];
  for (const raw of text.split(/[\n\r,;]+/)) {
    const entry = raw.trim();
    if (!entry) continue;
    if (isGuid(entry)) {
      const guid = entry.toLowerCase();
      if (!tenants.includes(guid)) tenants.push(guid);
    } else {
      invalid.push(entry);
    }
  }
  return { tenants, invalid };
}

export function isValidPackageVersion(version: string): boolean {
  return VERSION_RE.test(version.trim());
}

export function buildPackageDownloadUrl(gatewayName: string, version: string): string {
  const params = new URLSearchParams({
    gateway_name: gatewayName,
    version: version.trim() || DEFAULT_PACKAGE_VERSION,
  });
  return `/api/method/${MANIFEST}.download_teams_app_package?${params.toString()}`;
}

export function findCheck(diagnosis: TeamsDiagnosis | null, id: string): TeamsCheck | undefined {
  return diagnosis?.checks.find((c) => c.id === id);
}

export async function diagnoseTeams(gatewayName: string): Promise<TeamsDiagnosis> {
  try {
    const result = await call.post(`${DIAG}.teams_diagnose`, { gateway_name: gatewayName });
    return result?.message as TeamsDiagnosis;
  } catch (error) {
    handleFrappeError(error, 'Error checking the Teams connection');
  }
}

export async function getTeamsSupportBundle(gatewayName: string): Promise<Record<string, unknown>> {
  try {
    const result = await call.post(`${DIAG}.teams_support_bundle`, { gateway_name: gatewayName });
    return result?.message as Record<string, unknown>;
  } catch (error) {
    handleFrappeError(error, 'Error preparing the support bundle');
  }
}

export async function getTeamsSettings(gatewayName: string): Promise<TeamsSettings> {
  try {
    const result = await call.get(`${TENANT}.get_teams_settings`, { gateway: gatewayName });
    return result?.message as TeamsSettings;
  } catch (error) {
    handleFrappeError(error, 'Error loading the Teams settings');
  }
}

export async function saveTeamsAllowedTenants(gatewayName: string, tenants: string[]): Promise<TeamsSettings> {
  try {
    const result = await call.post(`${TENANT}.save_teams_settings`, {
      gateway: gatewayName,
      allowed_tenants: tenants.join('\n'),
    });
    return result?.message as TeamsSettings;
  } catch (error) {
    handleFrappeError(error, 'Error saving the allowed organisations');
  }
}

export async function saveTeamsPackageVersion(gatewayName: string, version: string): Promise<void> {
  try {
    await call.post(`${TENANT}.save_teams_settings`, {
      gateway: gatewayName,
      app_package_version: version.trim(),
    });
  } catch (error) {
    handleFrappeError(error, 'Error saving the app package version');
  }
}

export async function listTeamsLinks(gatewayName: string): Promise<TeamsLink[]> {
  try {
    const result = await call.get(`${IDENTITY}.list_teams_links`, { gateway: gatewayName });
    return (result?.message as TeamsLink[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error loading linked people');
  }
}

export function buildLinkParams(gatewayName: string, tenantId: string, aadObjectId: string, user: string) {
  return {
    gateway: gatewayName,
    tenant_id: tenantId.trim().toLowerCase(),
    aad_object_id: aadObjectId.trim().toLowerCase(),
    user: user.trim(),
  };
}

export async function linkTeamsUser(
  gatewayName: string,
  tenantId: string,
  aadObjectId: string,
  user: string
): Promise<void> {
  try {
    await call.post(`${IDENTITY}.link_teams_user`, buildLinkParams(gatewayName, tenantId, aadObjectId, user));
  } catch (error) {
    handleFrappeError(error, 'Error linking the person');
  }
}

export async function revokeTeamsLink(name: string): Promise<void> {
  try {
    await call.post(`${IDENTITY}.revoke_teams_link`, { name });
  } catch (error) {
    handleFrappeError(error, 'Error removing the link');
  }
}

export async function saveTeamsBotSettings(gatewayName: string, values: TeamsBotSettingsInput): Promise<TeamsSettings> {
  try {
    const result = await call.post(`${TENANT}.save_teams_settings`, {
      gateway: gatewayName,
      bot_handle: values.bot_handle.trim(),
      private_output_policy: values.private_output_policy,
      help_text_override: values.help_text_override.trim(),
    });
    return result?.message as TeamsSettings;
  } catch (error) {
    handleFrappeError(error, 'Error saving the bot settings');
  }
}
