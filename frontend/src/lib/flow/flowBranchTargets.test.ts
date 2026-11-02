import { describe, it, expect } from 'vitest';
import { buildBranchOptionLabels, findUpstreamNodeIds } from './flowBranchTargets';

describe('buildBranchOptionLabels', () => {
  it('keeps unique labels unchanged', () => {
    const labels = buildBranchOptionLabels([
      { id: 'n1', data: { label: 'Send email' } },
      { id: 'n2', data: { label: 'Wait' } },
    ]);
    expect(labels.get('n1')).toBe('Send email');
    expect(labels.get('n2')).toBe('Wait');
  });

  it('appends a short id suffix only to duplicated labels', () => {
    const labels = buildBranchOptionLabels([
      { id: 'abcdef123456', data: { label: 'Transform Data' } },
      { id: 'zz99', data: { label: 'Transform Data' } },
      { id: 'solo', data: { label: 'Loop' } },
    ]);
    expect(labels.get('abcdef123456')).toBe('Transform Data · abcdef12…');
    expect(labels.get('zz99')).toBe('Transform Data · zz99');
    expect(labels.get('solo')).toBe('Loop');
  });

  it('falls back to the node id when there is no label', () => {
    const labels = buildBranchOptionLabels([{ id: 'node-1', data: {} }]);
    expect(labels.get('node-1')).toBe('node-1');
  });

  it('marks upstream targets without removing them', () => {
    const labels = buildBranchOptionLabels(
      [
        { id: 'a', data: { label: 'Start' } },
        { id: 'b', data: { label: 'Check' } },
      ],
      new Set(['a']),
    );
    expect(labels.get('a')).toBe('Start  ↑ upstream — creates a loop');
    expect(labels.get('b')).toBe('Check');
  });
});

describe('findUpstreamNodeIds', () => {
  it('returns all transitive ancestors of the selected node', () => {
    const edges = [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
      { source: 'c', target: 'd' },
      { source: 'x', target: 'd' },
    ];
    expect([...findUpstreamNodeIds(edges, 'c')].sort()).toEqual(['a', 'b']);
    expect([...findUpstreamNodeIds(edges, 'd')].sort()).toEqual(['a', 'b', 'c', 'x']);
  });

  it('excludes downstream nodes and handles cycles without looping forever', () => {
    const edges = [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'a' },
      { source: 'b', target: 'c' },
    ];
    expect([...findUpstreamNodeIds(edges, 'a')].sort()).toEqual(['a', 'b']);
    expect([...findUpstreamNodeIds(edges, 'c')].sort()).toEqual(['a', 'b']);
  });

  it('returns an empty set when there is no selection', () => {
    expect(findUpstreamNodeIds([{ source: 'a', target: 'b' }], null).size).toBe(0);
  });
});
