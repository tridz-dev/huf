import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type { ElevenlabsSettingsDoc, HttpProviderSettingsDoc } from '@/types/integration.types';

/** One entry from `huf.ai.voice.api.list_engines()`. */
export interface VoiceEngineOption {
  key: string;
  label: string;
  kind: string;
}

/** One entry from `huf.ai.voice.api.get_config_schema()`. */
export interface VoiceConfigSchemaField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'select' | 'secret';
  default?: unknown;
  help_text?: string;
  options?: Array<{ value: string; label: string }>;
  visible_when?: Record<string, unknown>;
}

/** Fetch the registered voice engines available for agents to use. */
export async function listVoiceEngines(): Promise<VoiceEngineOption[]> {
  try {
    const result = await call.get('huf.ai.voice.api.list_engines');
    return (result.message as VoiceEngineOption[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching voice engines');
  }
}

/** Fetch the config schema declared by a given voice engine key. */
export async function getVoiceConfigSchema(engine: string): Promise<VoiceConfigSchemaField[]> {
  try {
    const result = await call.get('huf.ai.voice.api.get_config_schema', { engine });
    return (result.message as VoiceConfigSchemaField[]) || [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching voice engine configuration schema');
  }
}

export async function getElevenlabsSettings(): Promise<ElevenlabsSettingsDoc | undefined> {
  try {
    return await db.getDoc(doctype['Elevenlabs Settings'], doctype['Elevenlabs Settings']);
  } catch (error) {
    handleFrappeError(error, 'Error fetching Elevenlabs settings');
  }
}

export async function updateElevenlabsSettings(data: ElevenlabsSettingsDoc): Promise<void> {
  try {
    await db.updateDoc(doctype['Elevenlabs Settings'], doctype['Elevenlabs Settings'], data);
  } catch (error) {
    handleFrappeError(error, 'Error updating Elevenlabs settings');
    throw error;
  }
}

export async function getGroqSettings(): Promise<HttpProviderSettingsDoc | undefined> {
  try {
    return await db.getDoc(doctype['Groq Settings'], doctype['Groq Settings']);
  } catch (error) {
    handleFrappeError(error, 'Error fetching Groq settings');
  }
}

export async function updateGroqSettings(data: HttpProviderSettingsDoc): Promise<void> {
  try {
    await db.updateDoc(doctype['Groq Settings'], doctype['Groq Settings'], data);
  } catch (error) {
    handleFrappeError(error, 'Error updating Groq settings');
    throw error;
  }
}

export async function getOpenAISettings(): Promise<HttpProviderSettingsDoc | undefined> {
  try {
    return await db.getDoc(doctype['OpenAI Settings'], doctype['OpenAI Settings']);
  } catch (error) {
    handleFrappeError(error, 'Error fetching OpenAI settings');
  }
}

export async function updateOpenAISettings(data: HttpProviderSettingsDoc): Promise<void> {
  try {
    await db.updateDoc(doctype['OpenAI Settings'], doctype['OpenAI Settings'], data);
  } catch (error) {
    handleFrappeError(error, 'Error updating OpenAI settings');
    throw error;
  }
}
