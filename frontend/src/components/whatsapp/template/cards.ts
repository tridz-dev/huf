import { emptyButton, emptyCard, newCardLike, type TemplateWizardDraft, type WizardButton, type WizardButtonType, type WizardCard } from './draft';
import { WIZARD_LIMITS } from './rules';

/** Pure edits of a carousel draft's card list (the cards editor wires these to the wizard). */

export function addCard(draft: TemplateWizardDraft, id: string): TemplateWizardDraft {
  if (draft.cards.length >= WIZARD_LIMITS.cardsMax) return draft;
  return { ...draft, cards: [...draft.cards, newCardLike(draft.cards[0], id)] };
}

export function removeCard(draft: TemplateWizardDraft, index: number): TemplateWizardDraft {
  return { ...draft, cards: draft.cards.filter((_, i) => i !== index) };
}

export function moveCard(draft: TemplateWizardDraft, index: number, by: -1 | 1): TemplateWizardDraft {
  const to = index + by;
  if (to < 0 || to >= draft.cards.length) return draft;
  const cards = [...draft.cards];
  [cards[index], cards[to]] = [cards[to], cards[index]];
  return { ...draft, cards };
}

export function updateCard(draft: TemplateWizardDraft, index: number, patch: Partial<WizardCard>): TemplateWizardDraft {
  return { ...draft, cards: draft.cards.map((c, i) => (i === index ? { ...c, ...patch } : c)) };
}

export function updateCardButton(
  draft: TemplateWizardDraft,
  card: number,
  button: number,
  patch: Partial<WizardButton>,
): TemplateWizardDraft {
  const buttons = draft.cards[card]?.buttons.map((b, j) => (j === button ? { ...b, ...patch } : b));
  return buttons ? updateCard(draft, card, { buttons }) : draft;
}

/** Why a card button of this type cannot be added, or null. */
export function cardButtonBlocker(draft: TemplateWizardDraft, type: WizardButtonType): string | null {
  const first = draft.cards[0]?.buttons ?? [];
  if (first.length >= WIZARD_LIMITS.cardButtons) return `Up to ${WIZARD_LIMITS.cardButtons} buttons per card`;
  if (type === 'URL' && first.filter((b) => b.type === 'URL').length >= WIZARD_LIMITS.cardButtons) return 'Up to 2 website buttons';
  return null;
}

/** Add the same kind of button to EVERY card, so all cards keep an identical button set. */
export function addCardButton(draft: TemplateWizardDraft, type: 'QUICK_REPLY' | 'URL', idBase: string): TemplateWizardDraft {
  if (cardButtonBlocker(draft, type)) return draft;
  return {
    ...draft,
    cards: draft.cards.map((c, i) => ({ ...c, buttons: [...c.buttons, emptyButton(type, `${idBase}-${i}`)] })),
  };
}

export function removeCardButton(draft: TemplateWizardDraft, button: number): TemplateWizardDraft {
  return { ...draft, cards: draft.cards.map((c) => ({ ...c, buttons: c.buttons.filter((_, j) => j !== button) })) };
}

/** A carousel starts with two empty cards and one quick-reply button each. */
export function startCarousel(draft: TemplateWizardDraft, id: (n: number) => string): TemplateWizardDraft {
  if (draft.cards.length) return { ...draft, carousel: true };
  const mk = (n: number) => emptyCard(id(n), [emptyButton('QUICK_REPLY', `${id(n)}-b0`)]);
  return { ...draft, carousel: true, cards: [mk(1), mk(2)] };
}
