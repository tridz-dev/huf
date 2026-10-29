import { call } from '@/lib/frappe-sdk';

const BASE = 'huf.ai.channels.embedded_signup';

const unwrap = <T>(res: unknown): T =>
  (res && typeof res === 'object' && 'message' in res ? (res as { message: T }).message : res) as T;

export interface SignupConfig {
  enabled: boolean;
  app_id: string;
  config_id: string;
  graph_version: string;
}

export interface CompleteSignupArgs {
  code: string;
  waba_id: string;
  phone_number_id: string;
  business_id?: string;
  gateway_name?: string;
  pin?: string;
}

/** The access token is never part of this result. `pin` is present only when the server generated it. */
export interface CompleteSignupResult {
  gateway: string;
  setup_stage: string;
  webhook_url: string;
  verify_token_hint: string;
  warnings: string[];
  pin?: string;
}

export interface SignupSettings {
  enabled: boolean;
  mode: 'direct' | 'broker' | 'broker_server';
  facebook_app_id: string;
  config_id: string;
  graph_version: string;
  broker_url: string;
  tenant_id: string;
  app_secret_set: boolean;
  broker_api_key_set: boolean;
  broker_verify_token_set: boolean;
  /** broker_server: the URL to set as the Meta app's webhook callback. */
  broker_callback_url: string;
}

export type SignupSettingsPatch = Partial<Omit<SignupSettings, 'app_secret_set' | 'broker_api_key_set' | 'broker_verify_token_set' | 'broker_callback_url'>> & {
  /** Write-only: omit or leave empty to keep the stored value. */
  app_secret?: string;
  broker_api_key?: string;
  broker_verify_token?: string;
};

export async function getSignupConfig(): Promise<SignupConfig> {
  return unwrap<SignupConfig>(await call.get(`${BASE}.get_signup_config`, {}));
}

export async function completeSignup(args: CompleteSignupArgs): Promise<CompleteSignupResult> {
  return unwrap<CompleteSignupResult>(await call.post(`${BASE}.complete_signup`, { ...args }));
}

export async function getSignupSettings(): Promise<SignupSettings> {
  return unwrap<SignupSettings>(await call.get(`${BASE}.get_settings_admin`, {}));
}

export async function saveSignupSettings(patch: SignupSettingsPatch): Promise<SignupSettings> {
  return unwrap<SignupSettings>(await call.post(`${BASE}.save_settings`, { values: JSON.stringify(patch) }));
}
