export interface CredentialSchemaItem {
  key: string;
  label: string;
  required?: boolean;
  description?: string;
}

export interface IntegrationCredentialRow {
  name?: string;
  key: string;
  value?: string;
  description?: string;
}

export interface IntegrationRecipientRow {
  name?: string;
  recipient_name: string;
  recipient_id: string;
  user?: string;
}

export interface IntegrationServiceDoc {
  name: string;
  service_name: string;
  category: string;
  description?: string;
  documentation_url?: string;
  required_credentials?: string | CredentialSchemaItem[];
  is_builtin?: 0 | 1;
}

export interface IntegrationSettingsDoc {
  name: string;
  service: string;
  is_active: 0 | 1;
  is_default: 0 | 1;
  credentials?: IntegrationCredentialRow[];
  recipients?: IntegrationRecipientRow[];
  telegram_agent?: string;
  telegram_auto_setup_webhook?: 0 | 1;
  telegram_webhook_secret?: string;
  telegram_webhook_url?: string;
  telegram_webhook_status?: string;
  telegram_last_webhook_setup?: string;
  last_used?: string;
  last_error?: string;
  modified?: string;
}

export function parseRequiredCredentials(
  json: string | CredentialSchemaItem[] | undefined | null,
): CredentialSchemaItem[] {
  if (!json) return [];
  if (Array.isArray(json)) return json;
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function credentialsToMap(
  credentials: IntegrationCredentialRow[] | undefined,
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const cred of credentials ?? []) {
    if (cred.key) {
      map[cred.key] = cred.value ?? '';
    }
  }
  return map;
}

export function buildCredentialsPayload(
  schema: CredentialSchemaItem[],
  formValues: Record<string, string>,
  existingCredentials: IntegrationCredentialRow[] | undefined,
  isNew: boolean,
): IntegrationCredentialRow[] {
  const existingMap = credentialsToMap(existingCredentials);

  return schema.map((item) => {
    const formValue = formValues[item.key]?.trim() ?? '';
    const existingRow = existingCredentials?.find((c) => c.key === item.key);

    if (isNew) {
      return {
        key: item.key,
        value: formValue,
        description: item.label,
      };
    }

    // On edit: blank field keeps existing value
    const value = formValue || existingMap[item.key] || '';
    return {
      ...(existingRow?.name ? { name: existingRow.name } : {}),
      key: item.key,
      value,
      description: item.label,
    };
  });
}
