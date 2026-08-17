import { describe, expect, it } from 'vitest';
import { Workflow } from 'lucide-react';
import { getServiceIdentity } from './serviceIdentity';

describe('service identities', () => {
  it.each([
    ['telegram', 'Telegram'],
    ['slack', 'Slack'],
    ['whatsapp', 'WhatsApp'],
    ['discord', 'Discord'],
    ['teams', 'Microsoft Teams'],
    ['github', 'GitHub'],
    ['jira', 'Jira'],
    ['google_calendar', 'Google Calendar'],
    ['serpapi', 'SerpApi'],
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
