// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

afterEach(cleanup);

// Plain holder (not vi.fn): vitest's call tracking leaves rejected promises unhandled.
let impl: (n: string) => Promise<unknown> = () => Promise.resolve(null);
const calls: string[] = [];
vi.mock('@/services/artifactApi', () => ({
  getArtifact: (n: string) => {
    calls.push(n);
    return impl(n);
  },
}));
vi.mock('@/components/chat/ArtifactsPanel', () => ({
  isDocumentType: (t: string) => t === 'document' || t === 'markdown',
}));
vi.mock('@/components/chat/DocumentPreview', () => ({
  DocumentPreview: ({ artifactName }: { artifactName: string }) => (
    <div data-testid="doc-preview">{artifactName}</div>
  ),
}));
vi.mock('@/components/chat/ArtifactRenderer', () => ({
  ArtifactRenderer: ({ artifact }: { artifact: { type: string } }) => (
    <div data-testid="renderer">{artifact.type}</div>
  ),
}));

import { ArtifactPaneBody } from './ArtifactPaneBody';

describe('ArtifactPaneBody', () => {
  beforeEach(() => {
    calls.length = 0;
  });

  it.each(['document', 'markdown'])('uses DocumentPreview for %s', (t) => {
    render(<ArtifactPaneBody name="a1" artifactType={t} />);
    expect(screen.getByTestId('doc-preview').textContent).toBe('a1');
    expect(calls).toEqual([]);
  });

  it.each(['chart', 'jsx', 'mermaid', 'code', 'html'])('uses ArtifactRenderer for %s', async (t) => {
    impl = () => Promise.resolve({ name: 'a2', artifact_type: t, content: 'x', conversation: 'c' });
    render(<ArtifactPaneBody name="a2" artifactType={t} />);
    expect((await screen.findByTestId('renderer')).textContent).toBe(t);
    expect(screen.queryByTestId('doc-preview')).toBeNull();
  });

  it('shows an error when loading fails', async () => {
    impl = () => Promise.reject(new Error('boom'));
    render(<ArtifactPaneBody name="a3" artifactType="chart" />);
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('boom');
  });
});
