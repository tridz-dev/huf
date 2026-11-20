/**
 * Builder-form patterns (DESIGN.md §6.12): configure on one side, try on the
 * other. Domain-free; built only from components/ui, patterns and tokens.
 */
export { BuilderLayout, type BuilderLayoutProps } from './BuilderLayout';
export { FormSection, RequiredMark, FieldError, focusFirstError, ErrorSummary, type FormSectionProps, type FormError } from './FormSection';
export { ToggleReveal, ToggleRow, type ToggleRevealProps, type ToggleRowProps } from './ToggleReveal';
export { PresetSelector, CUSTOM_PRESET, type Preset, type PresetSelectorProps } from './PresetSelector';
export { TemplateChips, type TemplateChip } from './TemplateChips';
export { AutosaveStatus, savedAgo, type AutosaveState, type AutosaveStatusProps } from './AutosaveStatus';
export { TryPanel, Inspector, type TryMessage, type InspectorItem, type TryPanelProps } from './TryPanel';
export { StepCard, OneCardCreate, type StepCardProps, type OneCardCreateProps } from './StepCard';
