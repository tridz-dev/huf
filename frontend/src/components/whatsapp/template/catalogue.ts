import type { PreviewModel } from '../templateModel';
import type { TemplateCategoryId } from './draft';

export type KindAvailability = 'available' | 'disabled' | 'comingSoon';

export interface TemplateKind {
  id: string;
  /** Present for kinds that can be created today. */
  category: TemplateCategoryId | null;
  title: string;
  subtype: string;
  availability: KindAvailability;
  disabledReason?: string;
  description: string;
  goodFor: string[];
  customisable: string[];
  sample: PreviewModel;
}

export const TEMPLATE_KINDS: readonly TemplateKind[] = [
  {
    id: 'marketing_default',
    category: 'MARKETING',
    title: 'Marketing',
    subtype: 'Default',
    availability: 'available',
    description: 'Send promotions or information about your products, services or business.',
    goodFor: ['Offers and discounts', 'New arrivals and announcements', 'Win-back and re-engagement messages'],
    customisable: ['Header', 'Body', 'Footer', 'Buttons', 'Variables'],
    sample: {
      header: { kind: 'text', text: 'Summer sale is here' },
      body: 'Hi Alex, enjoy 20% off everything until Sunday. Tap below to see what is new.',
      footer: 'Reply STOP to opt out',
      buttons: [{ type: 'URL', text: 'Shop now' }],
    },
  },
  {
    id: 'utility_default',
    category: 'UTILITY',
    title: 'Utility',
    subtype: 'Default',
    availability: 'available',
    description: 'Send messages about an existing order or account, triggered by something the customer did.',
    goodFor: ['Order and delivery updates', 'Appointment reminders', 'Account and billing notices'],
    customisable: ['Header', 'Body', 'Footer', 'Buttons', 'Variables', 'Message validity'],
    sample: {
      header: null,
      body: 'Hi Alex, your order 4821 has shipped and should arrive on Friday.',
      footer: '',
      buttons: [{ type: 'URL', text: 'Track order' }],
    },
  },
  {
    id: 'authentication',
    category: null,
    title: 'Authentication',
    subtype: 'One-time password',
    availability: 'disabled',
    disabledReason: 'One-time password templates use a fixed WhatsApp format and are not available here yet.',
    description: 'Send codes that let customers verify a transaction or login.',
    goodFor: ['Sign-in codes', 'Transaction verification', 'Account recovery'],
    customisable: ['Code expiry', 'Security notice'],
    sample: {
      header: null,
      body: '123456 is your verification code. For your security, do not share this code.',
      footer: 'This code expires in 10 minutes',
      buttons: [{ type: 'URL', text: 'Copy code' }],
    },
  },
  {
    id: 'catalogue',
    category: null,
    title: 'Catalogue',
    subtype: 'Product messages',
    availability: 'comingSoon',
    description: 'Show products from your catalogue and let customers browse inside the chat.',
    goodFor: ['Product discovery', 'Abandoned cart reminders'],
    customisable: ['Body', 'Footer', 'Catalogue'],
    sample: {
      header: null,
      body: 'Hi Alex, here are a few items we think you will like.',
      footer: '',
      buttons: [{ type: 'URL', text: 'View catalogue' }],
    },
  },
  {
    id: 'flows',
    category: null,
    title: 'Flows',
    subtype: 'Structured forms',
    availability: 'comingSoon',
    description: 'Collect structured answers, such as bookings or surveys, in a guided form.',
    goodFor: ['Appointment booking', 'Feedback surveys', 'Lead capture'],
    customisable: ['Body', 'Footer', 'Flow'],
    sample: {
      header: null,
      body: 'Hi Alex, tell us how we did. It takes about a minute.',
      footer: '',
      buttons: [{ type: 'QUICK_REPLY', text: 'Start survey' }],
    },
  },
  {
    id: 'calling',
    category: null,
    title: 'Calling',
    subtype: 'Voice call invitations',
    availability: 'comingSoon',
    description: 'Invite customers to a WhatsApp call straight from a message.',
    goodFor: ['Support call-backs', 'Sales conversations'],
    customisable: ['Body', 'Footer', 'Call button'],
    sample: {
      header: null,
      body: 'Hi Alex, our team is ready to talk about your request.',
      footer: '',
      buttons: [{ type: 'PHONE_NUMBER', text: 'Call us' }],
    },
  },
];

export function kindById(id: string): TemplateKind | undefined {
  return TEMPLATE_KINDS.find((k) => k.id === id);
}

export function isSelectableKind(kind: TemplateKind): boolean {
  return kind.availability === 'available' && kind.category !== null;
}
