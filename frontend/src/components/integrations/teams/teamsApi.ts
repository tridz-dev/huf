import { call } from '@/lib/frappe-sdk';
import { normalizeVerifyResult, type VerifyResult } from './teamsOnboarding';

export interface TeamsManifestPackage {
  manifest: Record<string, unknown>;
  filename: string;
  content_base64: string;
}

/** GET huf.ai.teams.manifest.generate_teams_app_manifest -> {manifest, filename, content_base64}. */
export async function generateTeamsAppManifest(gatewayName: string): Promise<TeamsManifestPackage> {
  const response = await call.get('huf.ai.teams.manifest.generate_teams_app_manifest', {
    gateway_name: gatewayName,
  });
  return (response.message ?? response) as TeamsManifestPackage;
}

/** POST huf.ai.teams.diagnostics.verify_teams_connection -> {ok, steps[], message}. */
export async function verifyTeamsConnection(gatewayName: string): Promise<VerifyResult> {
  const response = await call.post('huf.ai.teams.diagnostics.verify_teams_connection', {
    gateway_name: gatewayName,
  });
  return normalizeVerifyResult(response?.message ?? response);
}
