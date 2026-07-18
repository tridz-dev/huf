import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';
import type { ElevenlabsSettingsDoc, HttpProviderSettingsDoc } from '@/types/integration.types';

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
