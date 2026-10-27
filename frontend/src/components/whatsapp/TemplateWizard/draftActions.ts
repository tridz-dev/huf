import { emptyButton, headerSampleKey, type TemplateWizardDraft, type WizardButtonType } from '../template/draft';
import { WIZARD_LIMITS } from '../template/rules';
import { convertVariableType, extractVariables, remapSamples, type VariableType } from '../template/variables';

/** Switch every variable in the header and body to the other style, moving samples with them. */
export function switchVariableType(draft: TemplateWizardDraft, to: VariableType): TemplateWizardDraft {
  if (draft.variableType === to) return draft;
  const body = convertVariableType(draft.body, to);
  const headerIsText = draft.header.type === 'text';
  const header = headerIsText ? convertVariableType(draft.header.text, to) : { text: draft.header.text, map: {} };
  const samples = remapSamples(remapSamples(draft.samples, body.map), header.map, 'header.');
  return { ...draft, variableType: to, body: body.text, header: { ...draft.header, text: header.text }, samples };
}

const isQuickReply = (t: WizardButtonType) => t === 'QUICK_REPLY';

/** Adds a button next to others of its kind so quick replies and call-to-action buttons stay grouped. */
export function addButton(draft: TemplateWizardDraft, type: WizardButtonType, id: string): TemplateWizardDraft {
  const list = draft.buttons;
  const last = list.map((b) => isQuickReply(b.type) === isQuickReply(type)).lastIndexOf(true);
  const at = last === -1 ? list.length : last + 1;
  return { ...draft, buttons: [...list.slice(0, at), emptyButton(type, id), ...list.slice(at)] };
}

export function moveButton(draft: TemplateWizardDraft, index: number, by: -1 | 1): TemplateWizardDraft {
  const to = index + by;
  if (to < 0 || to >= draft.buttons.length) return draft;
  const buttons = [...draft.buttons];
  [buttons[index], buttons[to]] = [buttons[to], buttons[index]];
  return { ...draft, buttons };
}

/** Why another button of this type cannot be added, or null. */
export function buttonBlocker(draft: TemplateWizardDraft, type: WizardButtonType): string | null {
  const count = (t: WizardButtonType) => draft.buttons.filter((b) => b.type === t).length;
  if (draft.buttons.length >= WIZARD_LIMITS.buttonsTotal) return `Up to ${WIZARD_LIMITS.buttonsTotal} buttons`;
  if (type === 'URL' && count('URL') >= WIZARD_LIMITS.urlButtons) return `Up to ${WIZARD_LIMITS.urlButtons} website buttons`;
  if (type === 'PHONE_NUMBER' && count(type) >= WIZARD_LIMITS.phoneButtons) return 'Only one phone button';
  if (type === 'COPY_CODE' && count(type) >= WIZARD_LIMITS.copyCodeButtons) return 'Only one offer code button';
  return null;
}

/** Variables that need an example value, header first. */
export function sampleVariables(draft: TemplateWizardDraft): { key: string; token: string; where: string }[] {
  const header = draft.header.type === 'text' ? extractVariables(draft.header.text, draft.variableType) : [];
  const body = extractVariables(draft.body, draft.variableType);
  return [
    ...header.slice(0, 1).map((token) => ({ key: headerSampleKey(token), token, where: 'Header' })),
    ...body.map((token) => ({ key: token, token, where: 'Body' })),
  ];
}

export function ttlLabel(seconds: number): string {
  if (seconds < 60) return `${seconds} seconds`;
  if (seconds < 3600) return `${seconds / 60} minutes`;
  const h = seconds / 3600;
  return `${h} ${h === 1 ? 'hour' : 'hours'}`;
}
