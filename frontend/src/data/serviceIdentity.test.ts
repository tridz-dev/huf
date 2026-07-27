import { describe, expect, it } from 'vitest';
import { Workflow } from 'lucide-react';
import { getServiceIdentity, messagingServiceNames } from './serviceIdentity';

describe('service identities', () => {
  it('classifies the supported messaging channels', () => {
    expect([...messagingServiceNames].sort()).toEqual([
      'discord',
      'microsoft_teams',
      'slack',
      'teams',
      'telegram',
      'vk',
      'wecom',
      'whatsapp',
    ]);
  });

  it.each([
    ['telegram', 'Telegram'],
    ['slack', 'Slack'],
    ['whatsapp', 'WhatsApp'],
    ['discord', 'Discord'],
    ['teams', 'Microsoft Teams'],
    ['github', 'GitHub'],
    ['jira', 'Jira'],
    ['google_calendar', 'Google Calendar'],
  ])('uses a mapped brand identity for %s', (service, title) => {
    const identity = getServiceIdentity(service);

    expect(identity.title).toBe(title);
    expect(identity.icon).not.toBe(Workflow);
  });

  it('uses a readable title and neutral icon for custom services', () => {
    expect(getServiceIdentity('internal_ticketing')).toEqual({
      title: 'Internal Ticketing',
      icon: Workflow,
    });
  });
});
