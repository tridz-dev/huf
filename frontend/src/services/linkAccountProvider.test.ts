import { describe, it, expect, vi, beforeEach } from 'vitest';

const get = vi.fn();
const post = vi.fn();
vi.mock('@/lib/frappe-sdk', () => ({ db: {}, call: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }));

import {
  confirmSelfLink,
  describeLinkError,
  parseLinkProvider,
  previewSelfLink,
  providerName,
} from './linkAccountApi';

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});

describe('parseLinkProvider', () => {
  it('reads p=teams', () => {
    expect(parseLinkProvider('?p=teams&token=x')).toBe('teams');
  });
  it('defaults to slack when absent or unknown', () => {
    expect(parseLinkProvider('')).toBe('slack');
    expect(parseLinkProvider('?token=x')).toBe('slack');
    expect(parseLinkProvider('?p=other')).toBe('slack');
    expect(parseLinkProvider('?p=TEAMS')).toBe('slack');
  });
});

describe('providerName', () => {
  it('names each app', () => {
    expect(providerName('slack')).toBe('Slack');
    expect(providerName('teams')).toBe('Teams');
  });
});

describe('describeLinkError with provider', () => {
  it('uses the app name', () => {
    expect(describeLinkError(new Error('x'), 'teams')).toMatch(/new one in Teams/);
    expect(describeLinkError(new Error('x'))).toMatch(/new one in Slack/);
  });
  it('explains the one-account-per-tenant refusal', () => {
    expect(describeLinkError(new Error('Your Huf account is already linked to another Teams account'), 'teams')).toMatch(
      /Your Huf account is already linked to another Teams/,
    );
  });
});

describe('endpoint routing', () => {
  it('calls Slack endpoints by default', async () => {
    get.mockResolvedValue({ message: { slack_label: 'U1', workspace_label: 'W' } });
    post.mockResolvedValue({ message: { linked: true, user: 'a' } });
    const preview = await previewSelfLink('tok');
    await confirmSelfLink('tok');
    expect(get).toHaveBeenCalledWith('huf.ai.gateways.identity.preview_self_link', { token: 'tok' });
    expect(post).toHaveBeenCalledWith('huf.ai.gateways.identity.confirm_self_link', { token: 'tok' });
    expect(preview.person_label).toBe('U1');
  });
  it('calls Teams endpoints for teams', async () => {
    get.mockResolvedValue({ message: { person_label: 'Ada', workspace_label: 'T' } });
    post.mockResolvedValue({ message: { linked: true, user: 'a' } });
    const preview = await previewSelfLink('tok', 'teams');
    await confirmSelfLink('tok', 'teams');
    expect(get).toHaveBeenCalledWith('huf.ai.gateways.teams_identity.preview_teams_link', { token: 'tok' });
    expect(post).toHaveBeenCalledWith('huf.ai.gateways.teams_identity.confirm_teams_link', { token: 'tok' });
    expect(preview.person_label).toBe('Ada');
  });
});
