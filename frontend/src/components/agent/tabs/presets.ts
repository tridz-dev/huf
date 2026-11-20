/**
 * Pure mappings between plain-language presets and the raw Agent fields.
 * Creativity <-> temperature; Thinking <-> reasoning_mode + reasoning_effort.
 * "custom" is returned whenever the stored values do not match a named preset,
 * so existing agents never lose a hand-tuned value.
 */

export type CreativityPreset = 'precise' | 'balanced' | 'creative';
export const CREATIVITY_PRESETS: Record<CreativityPreset, number> = {
  precise: 0.2,
  balanced: 0.7,
  creative: 1.0,
};
/** Values within this distance of a preset still count as that preset (slider step is 0.1). */
const TEMPERATURE_TOLERANCE = 0.05;

export function temperatureToPreset(temperature: number | null | undefined): CreativityPreset | 'custom' {
  if (typeof temperature !== 'number' || Number.isNaN(temperature)) return 'custom';
  for (const [preset, value] of Object.entries(CREATIVITY_PRESETS) as [CreativityPreset, number][]) {
    if (Math.abs(temperature - value) < TEMPERATURE_TOLERANCE) return preset;
  }
  return 'custom';
}

export function presetToTemperature(preset: CreativityPreset): number {
  return CREATIVITY_PRESETS[preset];
}

export type ThinkingPreset = 'off' | 'auto' | 'light' | 'deep';
export type ReasoningMode = 'Auto' | 'Off' | 'On';
export type ReasoningEffort = 'Auto' | 'Low' | 'Medium' | 'High';

export const THINKING_PRESETS: Record<ThinkingPreset, { reasoning_mode: ReasoningMode; reasoning_effort: ReasoningEffort }> = {
  off: { reasoning_mode: 'Off', reasoning_effort: 'Auto' },
  auto: { reasoning_mode: 'Auto', reasoning_effort: 'Auto' },
  light: { reasoning_mode: 'On', reasoning_effort: 'Low' },
  deep: { reasoning_mode: 'On', reasoning_effort: 'High' },
};

export function reasoningToPreset(mode?: string | null, effort?: string | null): ThinkingPreset | 'custom' {
  const m = mode || 'Auto';
  const e = effort || 'Auto';
  // With thinking forced off, effort is irrelevant.
  if (m === 'Off') return 'off';
  for (const [preset, v] of Object.entries(THINKING_PRESETS) as [ThinkingPreset, (typeof THINKING_PRESETS)[ThinkingPreset]][]) {
    if (preset !== 'off' && v.reasoning_mode === m && v.reasoning_effort === e) return preset;
  }
  return 'custom';
}

export function presetToReasoning(preset: ThinkingPreset) {
  return { ...THINKING_PRESETS[preset] };
}
